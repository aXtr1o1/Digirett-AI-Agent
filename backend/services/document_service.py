import logging
import hashlib
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
import fitz  # PyMuPDF
from langdetect import detect, LangDetectException

from config import settings
from db.redis_client import RedisClient
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

# ── Session constants ─────────────────────────────────────────────────────────
# ── Session constants (Moved to config.py) ───────────────────────────────────
SESSION_TTL_SECONDS  = settings.DOC_SESSION_TTL_SECONDS


class DocumentService:

    def __init__(
        self,
        redis_client: RedisClient,
        supabase_client: SupabaseClient,
    ) -> None:
        self._redis    = redis_client
        self._supabase = supabase_client
        logger.info("[OK] DocumentService initialized")
        if settings.DOC_TESTING_MODE:
            logger.info("[TEST] TESTING MODE ACTIVE - Document limits disabled for testing")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LANGUAGE DETECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def detect_document_language(self, text: str) -> str:
        
        try:
            if not text or len(text.strip()) < 50:
                logger.warning("Document too short for reliable language detection")
                return "english"
            
            # Detect language from first 1000 characters
            detected_lang = detect(text[:1000])
            
            # Normalize language codes
            if detected_lang in ('no', 'nb', 'nn'):
                return "norwegian"
            elif detected_lang in ('en', 'en-US', 'en-GB'):
                return "english"
            else:
                logger.info(f"🌐 Detected language code: {detected_lang}")
                return detected_lang
        except LangDetectException as exc:
            logger.warning(f"⚠️ Language detection failed | {exc} | defaulting to 'english'")
            return "english"
        except Exception as exc:
            logger.error(f"❌ Language detection error | {exc}")
            return "english"

    # ── Quota Session (User-based) ───────────────────────────────────
    def get_quota_session(self, user_id: str) -> Dict[str, Any]:
        """Fetch or initialize a 4-hour quota session for a user."""
        redis_key = f"quota:session:{user_id}"
        raw = self._redis.get_conversation_meta(redis_key)

        if raw:
            age = time.time() - raw.get("session_start", time.time())
            if age > SESSION_TTL_SECONDS:
                logger.info(f"♻️ Quota expired for user={user_id} — resetting")
                self._redis.clear_all_conversation_cache(redis_key)
                raw = None

        if not raw:
            raw = {
                "session_id":    str(uuid.uuid4()),
                "doc_count":     0,
                "turn_count":    0,
                "token_count":   0,
                "session_start": time.time(),
                "docs":          [],
            }
            self._redis.set_conversation_meta(redis_key, raw, ttl=SESSION_TTL_SECONDS)
            logger.info(
                f"🆕 New session created | user={user_id} | "
                f"session_id={raw['session_id']}"
            )

        return raw

    def _save_quota_session(self, user_id: str, session: Dict[str, Any]) -> None:
        """Save quota session back to Redis."""
        redis_key = f"quota:session:{user_id}"
        elapsed = time.time() - session.get("session_start", time.time())
        remaining_ttl = max(60, int(SESSION_TTL_SECONDS - elapsed))
        self._redis.set_conversation_meta(redis_key, session, ttl=remaining_ttl)

    # ── Conversation Session (Chat-based) ───────────────────────────
    def get_or_create_session(self, conversation_id: str) -> Dict[str, Any]:
        """Fetch or initialize a 4-hour document session for a chat."""
        redis_key = f"doc:session:{conversation_id}"
        raw = self._redis.get_conversation_meta(redis_key)
        
        if not raw:
            raw = {
                "session_id":    str(uuid.uuid4()),
                "doc_count":     0,
                "session_start": time.time(),
                "docs":          [],
            }
            self._redis.set_conversation_meta(redis_key, raw, ttl=SESSION_TTL_SECONDS)
        return raw

    def _save_session(self, conversation_id: str, session: Dict[str, Any]) -> None:
        """Persist updated session state back to Redis."""
        redis_key = f"doc:session:{conversation_id}"
        elapsed = time.time() - session.get("session_start", time.time())
        remaining_ttl = max(60, int(SESSION_TTL_SECONDS - elapsed))
        self._redis.set_conversation_meta(redis_key, session, ttl=remaining_ttl)

    def check_turn_limit(self, user_id: str, user_role: str = "user") -> Tuple[bool, int]:
        """Check if user has remaining turns. Admins/Lawyers bypass this."""
        if settings.DOC_TESTING_MODE or user_role in ["admin", "lawyer"]:
            return True, 999
        
        session = self.get_quota_session(user_id)
        turn_count = session.get("turn_count", 0)
        remaining = settings.DOC_MAX_TURNS_PER_SESSION - turn_count
        allowed = remaining > 0
        return allowed, remaining

    def check_token_limit(self, user_id: str, user_role: str = "user") -> Tuple[bool, int]:
        """Check if user has remaining token quota. Admins/Lawyers bypass this."""
        if settings.DOC_TESTING_MODE or user_role in ["admin", "lawyer"]:
            return True, 999999
        
        session = self.get_quota_session(user_id)
        token_count = session.get("token_count", 0)
        remaining = settings.DOC_MAX_TOKENS_PER_SESSION - token_count
        allowed = remaining > 0
        return allowed, remaining

    def increment_turn_count(self, user_id: str) -> int:
        """Increment the turn counter for the user's session."""
        session = self.get_quota_session(user_id)
        session["turn_count"] = session.get("turn_count", 0) + 1
        self._save_quota_session(user_id, session)

        # Also increment in Supabase for durability
        try:
            # Note: We still track turns in conversations table for analytics
            pass 
        except Exception:
            pass

        logger.info(
            f"🔢 Turn count: {session['turn_count']}/{settings.DOC_MAX_TURNS_PER_SESSION} | "
            f"user={user_id}"
        )
        return session["turn_count"]

    def increment_token_count(self, user_id: str, tokens: int) -> int:
        """Add tokens to the user's current session usage."""
        session = self.get_quota_session(user_id)
        session["token_count"] = session.get("token_count", 0) + tokens
        self._save_quota_session(user_id, session)
        
        logger.info(
            f"🪙 Token usage: {session['token_count']}/{settings.DOC_MAX_TOKENS_PER_SESSION} | "
            f"+{tokens} | user={user_id}"
        )
        return session["token_count"]

    def check_doc_limit(self, user_id: str, user_role: str = "user") -> Tuple[bool, int]:
        """Check if user can upload more documents. Admins/Lawyers bypass this."""
        if settings.DOC_TESTING_MODE or user_role in ["admin", "lawyer"]:
            return True, 999
        
        session = self.get_quota_session(user_id)
        doc_count = session.get("doc_count", 0)
        remaining = settings.DOC_MAX_PER_SESSION - doc_count
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
                
                # Safe OCR Fallback: Check if text has a "unicode problem" (garbled text)
                if text and (text.count('\ufffd') / len(text) > 0.05 or ("cid:" in text and text.count("cid:") > 5)):
                    try:
                        logger.info(f"🔍 Garbled text detected on page {page_num}. Attempting OCR fallback...")
                        # Try OCR (Requires Tesseract installed on the host)
                        text = page.get_text("text", textpage=page.get_textpage_ocr(flags=0, language="eng+nor"))
                    except Exception as ocr_exc:
                        logger.warning(f"⚠️ OCR fallback failed or not installed on page {page_num}: {ocr_exc}")

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
        user_role: str = "user",
    ) -> Dict[str, Any]:
        """
        Parse + store a document for a conversation session.

        Enforces: max 2 documents per session (configurable).
        Stores: Redis (text, TTL=4h) + Supabase (text + metadata).

        Returns a dict with document metadata.
        Raises ValueError if the session doc limit is exceeded.
        """
        # ── Enforce doc limit ────────────────────────────────────────────
        allowed, remaining = self.check_doc_limit(conversation_id, user_role=user_role)
        if not allowed:
            raise ValueError(
                f"Document upload limit reached. "
                f"You can upload a maximum of {settings.DOC_MAX_PER_SESSION} documents per session "
                f"(4-hour session). Your session will reset after 4 hours."
            )
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        ext = filename.rsplit(".", 1)[-1].lower()

        # ── Check if physical file exists in uploaded_files ──────────────
        existing_file = None
        is_duplicate = False
        try:
            res = self._supabase.table("uploaded_files") \
                .select("file_hash, extracted_text, char_count, storage_path, summary") \
                .eq("file_hash", file_hash) \
                .execute()
            if res.data:
                existing_file = res.data[0]
                is_duplicate = True
                logger.info(f"✨ Duplicate file detected by SHA-256 hash: {file_hash}")
        except Exception as exc:
            logger.warning(f"⚠️ Failed to query uploaded_files (possibly missing table): {exc}")

        if existing_file:
            extracted_text = existing_file["extracted_text"]
            char_count = existing_file["char_count"]
            storage_path = existing_file["storage_path"]
        else:
            # ── Parse ────────────────────────────────────────────────────────
            extracted_text = self.parse_document(file_bytes, filename)
            char_count = len(extracted_text)
            storage_path = f"uploads/{file_hash}.{ext}"

            # ── Store binary content in Supabase Storage ──────────────────────
            try:
                self._supabase._get().storage.from_("lovdata-documents").upload(
                    path=storage_path,
                    file=file_bytes,
                    file_options={"content-type": f"application/{ext}" if ext != 'pdf' else 'application/pdf'}
                )
                logger.info(f"💾 Binary file uploaded to storage | path={storage_path}")
            except Exception as storage_exc:
                logger.error(f"❌ Supabase Storage upload failed | {storage_exc}")
                # Don't fail completely if storage fails, RAG text is primary

            # ── Store in uploaded_files table ───────────────────────────────
            try:
                self._supabase.table("uploaded_files").insert({
                    "file_hash": file_hash,
                    "extracted_text": extracted_text,
                    "char_count": char_count,
                    "storage_path": storage_path,
                }).execute()
                logger.info(f"💾 File text and metadata stored in uploaded_files table | hash={file_hash}")
            except Exception as exc:
                # Handle race conditions / concurrent identical uploads gracefully
                logger.warning(f"⚠️ uploaded_files insert failed (may already exist from concurrent upload) | {exc}")

        # ── Detect language ──────────────────────────────────────────────
        document_language = self.detect_document_language(extracted_text)
        logger.info(f"🌐 Detected document language: {document_language}")

        # ── Generate document ID ─────────────────────────────────────────
        document_id = str(uuid.uuid4())

        # ── Update Quota ────────────────────────────────────────────────
        quota_session = self.get_quota_session(user_id)
        quota_session["doc_count"] = quota_session.get("doc_count", 0) + 1
        self._save_quota_session(user_id, quota_session)

        # ── Update Conversation Session ──────────────────────────────────
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
                "extracted_text": None,  # Save space by not duplicating extracted_text
                "char_count":     char_count,
                "language":       document_language,
                "upload_order":   upload_order,
                "is_active":      True,
                "created_at":     now.isoformat(),
                "expires_at":     expires_at.isoformat(),
                "file_hash":      file_hash,
            }).execute()
            logger.info(f"💾 Doc metadata saved in Supabase | document_id={document_id}")
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
            "language":    document_language,
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
            logger.warning(f"[WARN] Could not update document_count in Supabase | {exc}")

        doc_meta = {
            "document_id":  document_id,
            "file_name":    filename,
            "file_type":    ext,
            "char_count":   char_count,
            "language":     document_language,
            "upload_order": upload_order,
            "docs_remaining": settings.DOC_MAX_PER_SESSION - upload_order,
            "duplicate":    is_duplicate,
            "file_hash":    file_hash,
            "summary":      existing_file.get("summary") if existing_file else None,
        }
        logger.info(
            f"[OK] Document stored | id={document_id} | order={upload_order} | "
            f"chars={char_count:,} | conv={conversation_id} | duplicate={is_duplicate}"
        )
        return doc_meta

    def update_file_summary(self, file_hash: str, summary: str) -> None:
        """
        Updates the summary cache for a physical file in the database.
        """
        try:
            self._supabase.table("uploaded_files").update({
                "summary": summary
            }).eq("file_hash", file_hash).execute()
            logger.info(f"Updated summary cache in database for file_hash: {file_hash}")
        except Exception as e:
            logger.warning(f"[WARN] Failed to update summary in uploaded_files: {e}")

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
                .select("file_name, file_type, file_hash")
                .eq("document_id", document_id)
                .single()
                .execute()
            )
            
            if not doc_data.data:
                return None
            
            filename = doc_data.data["file_name"]
            ext = doc_data.data["file_type"]
            file_hash = doc_data.data.get("file_hash")
            
            # 2. Fetch from Storage
            if file_hash:
                storage_path = f"uploads/{file_hash}.{ext}"
            else:
                storage_path = f"uploads/{document_id}.{ext}"
                
            file_bytes = self._supabase._get().storage.from_("lovdata-documents").download(storage_path)
            
            content_type = "application/pdf" if ext == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            
            return file_bytes, filename, content_type
            
        except Exception as exc:
            logger.error(f"[ERROR] get_document_binary failed | id={document_id} | {exc}")
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
                logger.debug(f"[OK] Doc text cache hit | key={redis_text_key}")
                return text
        except Exception as exc:
            logger.warning(f"[WARN] Redis doc text get failed | {exc}")

        # ── Supabase fallback ─────────────────────────────────────────────
        try:
            response = (
                self._supabase.table("documents")
                .select("extracted_text, file_hash")
                .eq("document_id", document_id)
                .eq("is_active", True)
                .single()
                .execute()
            )
            if response.data:
                text = response.data.get("extracted_text")
                file_hash = response.data.get("file_hash")
                
                # Fetch from uploaded_files if extracted_text is not stored directly
                if not text and file_hash:
                    file_resp = (
                        self._supabase.table("uploaded_files")
                        .select("extracted_text")
                        .eq("file_hash", file_hash)
                        .single()
                        .execute()
                    )
                    if file_resp.data:
                        text = file_resp.data.get("extracted_text", "")
                
                # Re-warm Redis cache
                if text:
                    try:
                        self._redis._get().setex(
                            f"doc:text:{document_id}",
                            SESSION_TTL_SECONDS,
                            text,
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to update Redis cache for doc {document_id} | {exc}")
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

        # Reverse sort so the MOST RECENT document is at the top of the text.
        # This prevents the newest document from being truncated if the total size exceeds the LLM context.
        docs_sorted = sorted(docs, key=lambda d: d.get("upload_order", 0), reverse=True)
        parts = []
        for doc_meta in docs_sorted:
            text = self.get_document_text(doc_meta["document_id"])
            if text:
                parts.append(
                    f"=== Document {doc_meta['upload_order']}: "
                    f"{doc_meta['file_name']} ===\n\n{text}"
                )

        divider = "\n\n" + "=" * 60 + "\n\n"
        return divider.join(parts)

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

    def get_document_language(self, conversation_id: str) -> Optional[str]:
        """
        Retrieve the language of the documents in this conversation.
        Returns the language of the most recently uploaded document.
        If multiple documents are present, returns the latest one's language.
        Returns None if no documents exist.
        """
        docs = self.get_session_documents(conversation_id)
        if not docs:
            return None
        
        # Sort by upload_order descending to get the latest
        docs_sorted = sorted(docs, key=lambda d: d.get("upload_order", 0), reverse=True)
        latest_language = docs_sorted[0].get("language", "english")
        
        logger.info(f"📄 Document language for conv={conversation_id}: {latest_language}")
        return latest_language

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

    def save_summary_message(
        self,
        conversation_id: str,
        content: str,
        document_id: Optional[str] = None,
    ) -> str:
        """
        Inserts a document summary as an assistant message row into the messages table.
        This is what makes AI summaries reappear in chat history after refresh.
        """
        import uuid as _uuid
        message_id = str(_uuid.uuid4())

        try:
            self._supabase.table("messages").insert({
                "message_id":      message_id,
                "conversation_id": conversation_id,
                "role":            "assistant",
                "content":         content,
                "type":            "text",
                "file_name":       None,
                "sources":         [],
                "metadata":        {
                    "message_type": "document_summary",
                    "document_id": document_id,
                },
                "is_deleted":      False,
            }).execute()

            logger.info(
                f"💾 Summary message saved | message_id={message_id} | "
                f"conv={conversation_id}"
            )
            return message_id

        except Exception as exc:
            logger.error(f"❌ save_summary_message DB insert failed | {exc}", exc_info=True)
            raise