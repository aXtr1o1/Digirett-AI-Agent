"""
api/routes/documents.py

Document upload + session status + document retrieval endpoints.

POST /api/v1/documents/upload
GET  /api/v1/documents/session/{conversation_id}
GET  /api/v1/documents/conversation/{conversation_id}   ← NEW (Problem 1 fix)
"""

import logging
import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Injected from main.py via set_services() ─────────────────────────────────
_document_service = None
_llm_service = None


def set_services(document_service, llm_service=None) -> None:
    global _document_service, _llm_service
    _document_service = document_service
    _llm_service = llm_service


# ── Response models ───────────────────────────────────────────────────────────
class DocumentUploadResponse(BaseModel):
    document_id:    str
    file_name:      str
    file_type:      str
    char_count:     int
    upload_order:   int
    docs_remaining: int
    message:        str


class SessionStatusResponse(BaseModel):
    conversation_id:  str
    doc_count:        int
    turn_count:       int
    docs_remaining:   int
    turns_remaining:  int
    has_documents:    bool
    session_active:   bool


class DocumentMetaResponse(BaseModel):
    """Metadata for a single document — returned when restoring history."""
    document_id:  str
    file_name:    str
    char_count:   int
    upload_order: int


class ConversationDocumentsResponse(BaseModel):
    """
    All documents uploaded in a conversation's session.
    Called by the frontend on conversation load / history click
    so it can restore the document display without re-uploading.
    """
    conversation_id: str
    has_documents:   bool
    documents:       List[DocumentMetaResponse]


# ── Upload endpoint ───────────────────────────────────────────────────────────
@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    tags=["Documents"],
    summary="Upload a document (PDF or DOCX) for document-grounded QA",
)
async def upload_document(
    conversation_id: str = Form(...),
    user_id: str = Form(...),
    file: UploadFile = File(...),
):
    if _document_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document service not available.",
        )

    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("pdf", "docx", "doc"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: .{ext}. Please upload a PDF or DOCX file.",
        )

    MAX_SIZE = 20 * 1024 * 1024
    file_bytes = await file.read()
    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum allowed size is 20MB.",
        )

    allowed, docs_remaining = _document_service.check_doc_limit(conversation_id)
    if not allowed:
        session = _document_service.get_or_create_session(conversation_id)
        elapsed = time.time() - session.get("session_start", time.time())
        remaining_hours = max(0, round((4 * 3600 - elapsed) / 3600, 1))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Document upload limit reached. "
                f"You can upload a maximum of 2 documents per 4-hour session. "
                f"Your session resets in approximately {remaining_hours} hour(s)."
            ),
        )

    try:
        doc_meta = _document_service.store_document(
            conversation_id=conversation_id,
            user_id=user_id,
            file_bytes=file_bytes,
            filename=filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error(f"❌ Document upload failed | conv={conversation_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {exc}",
        )

    # ── Auto-summarize: stream summary back as assistant response ─────────
    if _llm_service is not None:
        doc_text = _document_service.get_document_text(doc_meta["document_id"])

        async def stream_summary():
            async for token in _llm_service.summarize_document_stream(doc_text):
                yield token

        logger.info(f"📝 Streaming auto-summary | doc_id={doc_meta['document_id']}")
        return StreamingResponse(stream_summary(), media_type="text/plain")

    remaining = doc_meta["docs_remaining"]
    message = (
        f"Document '{filename}' uploaded and parsed successfully. "
        + (
            f"1 more document can be uploaded this session."
            if remaining == 1
            else "No more documents can be uploaded this session."
            if remaining == 0
            else f"{remaining} more documents can be uploaded this session."
        )
    )

    return DocumentUploadResponse(
        document_id=doc_meta["document_id"],
        file_name=doc_meta["file_name"],
        file_type=doc_meta["file_type"],
        char_count=doc_meta["char_count"],
        upload_order=doc_meta["upload_order"],
        docs_remaining=remaining,
        message=message,
    )


# ── Session status endpoint ───────────────────────────────────────────────────
@router.get(
    "/documents/session/{conversation_id}",
    response_model=SessionStatusResponse,
    tags=["Documents"],
    summary="Get document session status for a conversation",
)
async def get_session_status(conversation_id: str):
    if _document_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document service not available.",
        )

    session = _document_service.get_or_create_session(conversation_id)
    doc_count  = session.get("doc_count", 0)
    turn_count = session.get("turn_count", 0)

    from services.document_service import MAX_DOCS_PER_SESSION, MAX_TURNS_PER_SESSION

    return SessionStatusResponse(
        conversation_id=conversation_id,
        doc_count=doc_count,
        turn_count=turn_count,
        docs_remaining=max(0, MAX_DOCS_PER_SESSION - doc_count),
        turns_remaining=max(0, MAX_TURNS_PER_SESSION - turn_count),
        has_documents=_document_service.has_documents(conversation_id),
        session_active=True,
    )


# ── NEW: Conversation documents endpoint (Problem 1 fix) ─────────────────────
@router.get(
    "/documents/conversation/{conversation_id}",
    response_model=ConversationDocumentsResponse,
    tags=["Documents"],
    summary="Get all documents uploaded in a conversation (for history restore)",
)
async def get_conversation_documents(conversation_id: str):
    """
    Called by the frontend when a user opens a conversation from history.
    Returns the list of documents uploaded in that conversation's session.

    Two sources are checked in order:
      1. Redis (fast — if session is still alive within 4h)
      2. Supabase (persistent — if Redis has expired, reads from documents table)

    This ensures documents are visible even after a page refresh or
    switching between conversations in the sidebar.
    """
    if _document_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document service not available.",
        )

    # ── Try Redis first (fast path) ───────────────────────────────────────
    docs_meta = _document_service.get_session_documents(conversation_id)

    # ── Supabase fallback (Redis expired or server restarted) ─────────────
    if not docs_meta:
        try:
            response = (
                _document_service._supabase.table("documents")
                .select("document_id, file_name, char_count, upload_order")
                .eq("conversation_id", conversation_id)
                .eq("is_active", True)
                .order("upload_order", desc=False)
                .execute()
            )
            rows = response.data or []
            if rows:
                # Re-warm Redis session with Supabase data so subsequent
                # queries can find the document text
                session = _document_service.get_or_create_session(conversation_id)
                for row in rows:
                    doc_id = row["document_id"]
                    # Only add if not already tracked in session
                    existing_ids = {d["document_id"] for d in session.get("docs", [])}
                    if doc_id not in existing_ids:
                        # Re-fetch text from Supabase to re-warm Redis text cache
                        text_response = (
                            _document_service._supabase.table("documents")
                            .select("extracted_text")
                            .eq("document_id", doc_id)
                            .single()
                            .execute()
                        )
                        if text_response.data:
                            extracted_text = text_response.data.get("extracted_text", "")
                            if extracted_text:
                                from services.document_service import SESSION_TTL_SECONDS
                                try:
                                    _document_service._redis._get().setex(
                                        f"doc:text:{doc_id}",
                                        SESSION_TTL_SECONDS,
                                        extracted_text,
                                    )
                                except Exception as redis_exc:
                                    logger.warning(
                                        f"⚠️ Could not re-warm Redis for doc {doc_id} | {redis_exc}"
                                    )
                        session["docs"].append({
                            "document_id":  row["document_id"],
                            "file_name":    row["file_name"],
                            "char_count":   row["char_count"],
                            "upload_order": row["upload_order"],
                        })
                        session["doc_count"] = max(
                            session.get("doc_count", 0), row["upload_order"]
                        )

                _document_service._save_session(conversation_id, session)
                docs_meta = session["docs"]
                logger.info(
                    f"📂 Restored {len(docs_meta)} doc(s) from Supabase for "
                    f"conv={conversation_id}"
                )
        except Exception as exc:
            logger.error(
                f"❌ Supabase document restore failed | conv={conversation_id} | {exc}",
                exc_info=True,
            )
            docs_meta = []

    return ConversationDocumentsResponse(
        conversation_id=conversation_id,
        has_documents=bool(docs_meta),
        documents=[
            DocumentMetaResponse(
                document_id=d["document_id"],
                file_name=d["file_name"],
                char_count=d["char_count"],
                upload_order=d["upload_order"],
            )
            for d in sorted(docs_meta, key=lambda x: x.get("upload_order", 0))
        ],
    )