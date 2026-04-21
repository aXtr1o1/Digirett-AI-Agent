"""
services/document_service.py

Handles the full document lifecycle:
  1. Parse  — extract text from PDF/DOCX using PyMuPDF (fitz)
  2. Store  — persist in both Redis (fast, TTL-scoped) and Supabase (durable)
  3. Retrieve — load doc text for a given conversation/session
  4. Session enforcement — 2 doc limit + 10 turn limit per 4-hour session

Redis key schema (new keys, zero collision with existing keys):
  doc:session:<session_id>          → { doc_count, turn_count, session_start, docs: [...] }
  doc:text:<document_id>            → raw extracted text (TTL = 4h)

Supabase tables used (after running 001_documents.sql):
  documents                         → document metadata + extracted_text
  conversations.session_turn_count  → incremented on every user turn
  conversations.document_count      → incremented on every doc upload
  conversations.session_id          → links conversation to a Redis session
"""

import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from config import settings
from db.redis_client import RedisClient
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

# ── Session constants ─────────────────────────────────────────────────────────
SESSION_TTL_SECONDS  = 4 * 60 * 60   # 4 hours
MAX_DOCS_PER_SESSION = 2
MAX_TURNS_PER_SESSION = 10


class DocumentService:

    def __init__(
        self,
        redis_client: RedisClient,
        supabase_client: SupabaseClient,
    ) -> None:
        self._redis    = redis_client
        self._supabase = supabase_client
        logger.info("✅ DocumentService initialized")
        if settings.DOC_TESTING_MODE:
            logger.info("🧪 TESTING MODE ACTIVE - Document limits disabled for testing")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SESSION MANAGEMENT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_or_create_session(self, conversation_id: str) -> Dict[str, Any]:
        """
        Load the session state for a conversation from Redis.
        Creates a fresh session if none exists.

        Returns a dict with:
          session_id    : str
          doc_count     : int  (0-2)
          turn_count    : int  (0-10)
          session_start : float (unix timestamp)
          docs          : list of {document_id, file_name, char_count}
        """
        redis_key = f"doc:session:{conversation_id}"
        raw = self._redis.get_conversation_meta(redis_key)

        if raw:
            # Check if the session has expired (belt-and-suspenders — Redis TTL handles
            # it too, but an explicit age check is safer)
            age = time.time() - raw.get("session_start", time.time())
            if age > SESSION_TTL_SECONDS:
                logger.info(
                    f"♻️  Session expired for conv={conversation_id} — creating new session"
                )
                self._redis.clear_all_conversation_cache(redis_key)
                raw = None

        if not raw:
            raw = {
                "session_id":    str(uuid.uuid4()),
                "doc_count":     0,
                "turn_count":    0,
                "session_start": time.time(),
                "docs":          [],
            }
            self._redis.set_conversation_meta(redis_key, raw, ttl=SESSION_TTL_SECONDS)
            logger.info(
                f"🆕 New session created | conv={conversation_id} | "
                f"session_id={raw['session_id']}"
            )

        return raw

    def _save_session(self, conversation_id: str, session: Dict[str, Any]) -> None:
        """Persist updated session state back to Redis."""
        redis_key = f"doc:session:{conversation_id}"
        # Remaining TTL = SESSION_TTL - elapsed
        elapsed = time.time() - session.get("session_start", time.time())
        remaining_ttl = max(60, int(SESSION_TTL_SECONDS - elapsed))
        self._redis.set_conversation_meta(redis_key, session, ttl=remaining_ttl)

    def check_turn_limit(self, conversation_id: str) -> Tuple[bool, int]:
        """
        Check if the user has hit the 10-turn limit.
        
        ⚠️  TESTING MODE OVERRIDE: If DOC_TESTING_MODE=True, always allows queries.

        Returns:
            (allowed: bool, turns_remaining: int)
        """
        # ┌─━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┐
        # │ TESTING MODE — Skip turn limit enforcement                  │
        # └─━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┘
        if settings.DOC_TESTING_MODE:
            logger.debug(f"⏭️  TEST_MODE: Turn limit bypassed | conv={conversation_id}")
            return True, 999
        
        session = self.get_or_create_session(conversation_id)
        turn_count = session.get("turn_count", 0)
        remaining = MAX_TURNS_PER_SESSION - turn_count
        allowed = remaining > 0
        return allowed, remaining

    def increment_turn_count(self, conversation_id: str) -> int:
        """
        Increment the turn counter for this conversation session.
        Returns the new turn count.
        Called by RAGService BEFORE processing each query.
        """
        session = self.get_or_create_session(conversation_id)
        session["turn_count"] = session.get("turn_count", 0) + 1
        self._save_session(conversation_id, session)

        # Also increment in Supabase for durability
        try:
            self._supabase.table("conversations").update({
                "session_turn_count": session["turn_count"]
            }).eq("conversation_id", conversation_id).execute()
        except Exception as exc:
            logger.warning(f"⚠️ Could not update session_turn_count in Supabase | {exc}")

        logger.info(
            f"🔢 Turn count: {session['turn_count']}/{MAX_TURNS_PER_SESSION} | "
            f"conv={conversation_id}"
        )
        return session["turn_count"]

    def check_doc_limit(self, conversation_id: str) -> Tuple[bool, int]:
        """
        Check if the user can still upload a document this session.
        
        ⚠️  TESTING MODE OVERRIDE: If DOC_TESTING_MODE=True, always allows uploads.

        Returns:
            (allowed: bool, docs_remaining: int)
        """
        # ┌─━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┐
        # │ TESTING MODE — Skip document limit enforcement              │
        # └─━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┘
        if settings.DOC_TESTING_MODE:
            logger.debug(f"⏭️  TEST_MODE: Document limit bypassed | conv={conversation_id}")
            return True, 999
        
        session = self.get_or_create_session(conversation_id)
        doc_count = session.get("doc_count", 0)
        remaining = MAX_DOCS_PER_SESSION - doc_count
        allowed = remaining > 0
        return allowed, remaining

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DOCUMENT PARSING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def parse_document(self, file_bytes: bytes, filename: str) -> str:
        """
        Extract text from PDF or DOCX using PyMuPDF.

        Args:
            file_bytes: Raw bytes of the uploaded file.
            filename:   Original filename (used to detect type).

        Returns:
            Extracted text as a single string.

        Raises:
            ValueError: If the file type is unsupported or parsing fails.
        """
        ext = filename.rsplit(".", 1)[-1].lower()

        if ext not in ("pdf", "docx", "doc"):
            raise ValueError(
                f"Unsupported file type: .{ext}. "
                "Only PDF and DOCX files are supported."
            )

        try:
            # PyMuPDF handles both PDF and DOCX natively
            doc = fitz.open(stream=file_bytes, filetype=ext if ext == "pdf" else "docx")
            pages = []
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text("text")
                if text.strip():
                    pages.append(f"[Page {page_num + 1}]\n{text.strip()}")
            doc.close()

            extracted = "\n\n".join(pages)

            if not extracted.strip():
                raise ValueError(
                    "Document appears to be empty or contains only images. "
                    "Text extraction returned no content."
                )

            # Clean up excessive whitespace while preserving structure
            extracted = re.sub(r"\n{4,}", "\n\n\n", extracted)
            extracted = re.sub(r" {3,}", "  ", extracted)

            logger.info(
                f"📄 Parsed '{filename}' | {len(pages)} pages | "
                f"{len(extracted):,} chars"
            )
            return extracted

        except fitz.FileDataError as exc:
            raise ValueError(f"Could not parse document '{filename}': {exc}") from exc
        except Exception as exc:
            raise ValueError(
                f"Document parsing failed for '{filename}': {exc}"
            ) from exc

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STORE DOCUMENT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def store_document(
        self,
        conversation_id: str,
        user_id: str,
        file_bytes: bytes,
        filename: str,
    ) -> Dict[str, Any]:
        """
        Parse + store a document for a conversation session.

        Enforces: max 2 documents per session.
        Stores: Redis (text, TTL=4h) + Supabase (text + metadata).

        Returns a dict with document metadata.
        Raises ValueError if the session doc limit is exceeded.
        """
        # ── Enforce doc limit ────────────────────────────────────────────
        allowed, remaining = self.check_doc_limit(conversation_id)
        if not allowed:
            raise ValueError(
                f"Document upload limit reached. "
                f"You can upload a maximum of {MAX_DOCS_PER_SESSION} documents per session "
                f"(4-hour session). Your session will reset after 4 hours."
            )

        # ── Parse ────────────────────────────────────────────────────────
        ext = filename.rsplit(".", 1)[-1].lower()
        extracted_text = self.parse_document(file_bytes, filename)
        char_count = len(extracted_text)

        # ── Generate document ID ─────────────────────────────────────────
        document_id = str(uuid.uuid4())

        # ── Load session ─────────────────────────────────────────────────
        session = self.get_or_create_session(conversation_id)
        upload_order = session["doc_count"] + 1

        # ── Store in Redis (text only, 4h TTL) ────────────────────────────
        redis_text_key = f"doc:text:{document_id}"
        try:
            self._redis._get().setex(
                redis_text_key,
                SESSION_TTL_SECONDS,
                extracted_text,
            )
            logger.info(f"💾 Doc text cached in Redis | key={redis_text_key}")
        except Exception as exc:
            logger.error(f"❌ Redis doc text store failed | {exc}")
            raise

        # ── Store in Supabase (Metadata) ───────────────────────────────────
        try:
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)

            self._supabase.table("documents").insert({
                "document_id":    document_id,
                "conversation_id": conversation_id,
                "user_id":        user_id,
                "session_id":     session["session_id"],
                "file_name":      filename,
                "file_type":      ext,
                "extracted_text": extracted_text,
                "char_count":     char_count,
                "upload_order":   upload_order,
                "is_active":      True,
                "created_at":     now.isoformat(),
                "expires_at":     expires_at.isoformat(),
            }).execute()
            logger.info(f"💾 Doc metadata saved in Supabase | document_id={document_id}")
            
            # ── Store binary content in Supabase Storage ──────────────────────
            # Bucket: 'lovdata-documents' | Path: 'uploads/{document_id}.{ext}'
            try:
                storage_path = f"uploads/{document_id}.{ext}"
                self._supabase._get().storage.from_("lovdata-documents").upload(
                    path=storage_path,
                    file=file_bytes,
                    file_options={"content-type": f"application/{ext}" if ext != 'pdf' else 'application/pdf'}
                )
                logger.info(f"💾 Binary file uploaded to storage | path={storage_path}")
            except Exception as storage_exc:
                logger.error(f"❌ Supabase Storage upload failed | {storage_exc}")
                # We don't fail the whole request since RAG can still work with the text
                
        except Exception as exc:
            logger.error(f"❌ Supabase doc store failed | {exc}")
            # Don't raise — Redis has the text, pipeline can still work
            logger.warning("⚠️ Continuing with Redis-only storage")

        # ── Update session state ──────────────────────────────────────────
        session["doc_count"] = upload_order
        session["docs"].append({
            "document_id": document_id,
            "file_name":   filename,
            "char_count":  char_count,
            "upload_order": upload_order,
        })
        self._save_session(conversation_id, session)

        # Update conversation.document_count in Supabase
        try:
            self._supabase.table("conversations").update({
                "document_count": upload_order,
                "session_id":     session["session_id"],
            }).eq("conversation_id", conversation_id).execute()
        except Exception as exc:
            logger.warning(f"⚠️ Could not update document_count in Supabase | {exc}")

        doc_meta = {
            "document_id":  document_id,
            "file_name":    filename,
            "file_type":    ext,
            "char_count":   char_count,
            "upload_order": upload_order,
            "docs_remaining": MAX_DOCS_PER_SESSION - upload_order,
        }
        logger.info(
            f"✅ Document stored | id={document_id} | order={upload_order} | "
            f"chars={char_count:,} | conv={conversation_id}"
        )
        return doc_meta

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RETRIEVE DOCUMENT TEXT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_document_binary(self, document_id: str) -> Optional[Tuple[bytes, str, str]]:
        """
        Retrieve the original binary document content and metadata.
        Returns: (file_bytes, filename, content_type)
        """
        try:
            # 1. Get metadata to know the extension/type
            doc_data = (
                self._supabase.table("documents")
                .select("file_name, file_type")
                .eq("document_id", document_id)
                .single()
                .execute()
            )
            
            if not doc_data.data:
                return None
            
            filename = doc_data.data["file_name"]
            ext = doc_data.data["file_type"]
            
            # 2. Fetch from Storage
            storage_path = f"uploads/{document_id}.{ext}"
            file_bytes = self._supabase._get().storage.from_("lovdata-documents").download(storage_path)
            
            content_type = "application/pdf" if ext == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            
            return file_bytes, filename, content_type
            
        except Exception as exc:
            logger.error(f"❌ get_document_binary failed | id={document_id} | {exc}")
            return None

    def get_document_text(self, document_id: str) -> Optional[str]:
        """
        Retrieve extracted document text.
        Tries Redis first (fast path), falls back to Supabase.
        """
        # ── Redis fast path ───────────────────────────────────────────────
        try:
            redis_text_key = f"doc:text:{document_id}"
            text = self._redis._get().get(redis_text_key)
            if text:
                logger.debug(f"✅ Doc text cache hit | key={redis_text_key}")
                return text
        except Exception as exc:
            logger.warning(f"⚠️ Redis doc text get failed | {exc}")

        # ── Supabase fallback ─────────────────────────────────────────────
        try:
            response = (
                self._supabase.table("documents")
                .select("extracted_text")
                .eq("document_id", document_id)
                .eq("is_active", True)
                .single()
                .execute()
            )
            if response.data:
                text = response.data.get("extracted_text", "")
                # Re-warm Redis cache
                try:
                    self._redis._get().setex(
                        f"doc:text:{document_id}",
                        SESSION_TTL_SECONDS,
                        text,
                    )
                except Exception:
                    pass
                return text
        except Exception as exc:
            logger.error(f"❌ Supabase doc text get failed | {exc}")

        return None

    def get_session_documents(self, conversation_id: str) -> List[Dict[str, Any]]:
        """
        Get metadata for all documents uploaded in this conversation's session.
        Returns list of {document_id, file_name, char_count, upload_order}.
        """
        session = self.get_or_create_session(conversation_id)
        return session.get("docs", [])

    def get_latest_document_text(self, conversation_id: str) -> Optional[str]:
        """
        Convenience method: get the text of the most recently uploaded document
        for a conversation. Used by RAGService to inject doc context.
        """
        docs = self.get_session_documents(conversation_id)
        if not docs:
            return None

        # Sort by upload_order descending, take the latest
        docs_sorted = sorted(docs, key=lambda d: d.get("upload_order", 0), reverse=True)
        latest_doc_id = docs_sorted[0]["document_id"]
        return self.get_document_text(latest_doc_id)

    def get_all_session_document_texts(self, conversation_id: str) -> str:
        """
        Get concatenated text from ALL documents uploaded in this session.
        Used when the user asks a question that might span multiple uploaded docs.
        Documents are separated by a clear divider.
        """
        docs = self.get_session_documents(conversation_id)
        if not docs:
            return ""

        docs_sorted = sorted(docs, key=lambda d: d.get("upload_order", 0))
        parts = []
        for doc_meta in docs_sorted:
            text = self.get_document_text(doc_meta["document_id"])
            if text:
                parts.append(
                    f"=== Document {doc_meta['upload_order']}: "
                    f"{doc_meta['file_name']} ===\n\n{text}"
                )

        return "\n\n{'='*60}\n\n".join(parts)

    def has_documents(self, conversation_id: str) -> bool:
        """Check if the current session has at least one uploaded document."""
        session = self.get_or_create_session(conversation_id)
        return len(session.get("docs", [])) > 0

    def get_doc_summary(self, conversation_id: str) -> Optional[str]:
        """
        Return first 500 chars of the latest document for the classifier.
        """
        text = self.get_latest_document_text(conversation_id)
        if not text:
            return None
        return text[:500]

    def save_file_message(
    self,
    conversation_id: str,
    role: str,
    content: Optional[str],
    file_name: str,
    metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Inserts a file-upload message row into the messages table.
        This is what makes uploaded files reappear in chat history after refresh.
        """
        import uuid as _uuid
        message_id = str(_uuid.uuid4())

        try:
            self._supabase.table("messages").insert({
                "message_id":      message_id,
                "conversation_id": conversation_id,
                "role":            role,
                "content":         content or "",
                "type":            "file-with-text",
                "file_name":       file_name,
                "sources":         [],
                "metadata":        {"message_type": "file_upload", "document_id": metadata.get("document_id") if isinstance(metadata, dict) else None},
                "is_deleted":      False,
            }).execute()

            logger.info(
                f"💾 File message saved | message_id={message_id} | "
                f"file={file_name} | conv={conversation_id}"
            )
            return message_id

        except Exception as exc:
            logger.error(f"❌ save_file_message DB insert failed | {exc}", exc_info=True)
            raise