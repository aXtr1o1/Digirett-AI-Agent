"""
Document upload + session status + document retrieval endpoints.

POST /api/v1/documents/upload
GET  /api/v1/documents/session/{conversation_id}
GET  /api/v1/documents/conversation/{conversation_id}  
"""

import logging
import time
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from core.auth import ClerkUser, get_current_user
from fastapi import Depends

logger = logging.getLogger(__name__)
router = APIRouter()

_document_service = None
_llm_service = None
_user_service = None


def set_services(document_service, llm_service=None, user_service=None) -> None:
    global _document_service, _llm_service, _user_service
    _document_service = document_service
    _llm_service = llm_service
    _user_service = user_service


class DocumentUploadResponse(BaseModel):
    document_id:    str
    file_name:      str
    file_type:      str
    char_count:     int
    upload_order:   int
    docs_remaining: int
    message:        str
    duplicate:      bool = False


class SessionStatusResponse(BaseModel):
    conversation_id:  str
    doc_count:        int
    turn_count:       int
    token_count:      int = 0
    docs_remaining:   int
    turns_remaining:  int
    tokens_remaining: int = 0
    has_documents:    bool
    session_active:   bool
    reset_at:         Optional[str] = None
    docs:             list = []


class FileMessageRequest(BaseModel):
    role:        str
    content:     Optional[str] = None
    type:        str = "file-with-text"
    file_name:   str
    document_id: Optional[str] = None


# ── Upload endpoint ───────────────────────────────────────────────────────────
@router.post(
    "/documents/upload",
    tags=["Documents"],
    summary="Upload a document (PDF or DOCX) for document-grounded QA",
)
async def upload_document(
    conversation_id: str = Form(...),
    file: UploadFile = File(...),
    user: ClerkUser = Depends(get_current_user),
):
    if _document_service is None or _user_service is None:
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

    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    allowed, docs_remaining = _document_service.check_doc_limit(internal_user_id, user_role=user.role)
    if not allowed:
        session = _document_service.get_or_create_session(internal_user_id)
        elapsed = time.time() - session.get("session_start", time.time())
        from config import settings
        remaining_hours = max(0, round((settings.DOC_SESSION_TTL_SECONDS - elapsed) / 3600, 1))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Document upload limit reached. "
                f"You can upload a maximum of {settings.DOC_MAX_PER_SESSION} documents per session. "
                f"Your session resets in approximately {remaining_hours} hour(s)."
            ),
        )
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    try:
        doc_meta = _document_service.store_document(
            conversation_id=conversation_id,
            user_id=internal_user_id,
            file_bytes=file_bytes,
            filename=filename,
            user_role=user.role
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error(f"❌ Document upload failed | conv={conversation_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {exc}",
        )

    # ── Auto-summarize via streaming ──────────────────────────────────────
    # KEY CHANGE: we now add file_name as a response header so the frontend
    # can read it even from a StreamingResponse
    if _llm_service is not None:
        cached_summary = doc_meta.get("summary")
        
        if cached_summary:
            import asyncio
            async def stream_summary():
                words = cached_summary.split(" ")
                for i in range(0, len(words), 5):
                    chunk = " ".join(words[i:i+5]) + " "
                    yield chunk
                    await asyncio.sleep(0.01) # fast simulation of LLM stream

            logger.info(f"⚡ Streaming cached auto-summary | doc_id={doc_meta['document_id']}")
        else:
            doc_text = _document_service.get_document_text(doc_meta["document_id"])
            
            accumulated = []
            async def stream_summary():
                async for token in _llm_service.summarize_document_stream(doc_text):
                    accumulated.append(token)
                    yield token
                
                # Save once complete
                summary_str = "".join(accumulated).strip()
                if summary_str and doc_meta.get("file_hash"):
                    _document_service.update_file_summary(doc_meta["file_hash"], summary_str)

            logger.info(f"📝 Streaming new auto-summary | doc_id={doc_meta['document_id']}")
        
        import urllib.parse
        filename_encoded = urllib.parse.quote(filename)
        is_duplicate_str = "true" if doc_meta.get("duplicate", False) else "false"
        
        return StreamingResponse(
            stream_summary(),
            media_type="text/plain",
            headers={
                # Frontend reads these headers to know the upload succeeded
                "X-Document-Id":   doc_meta["document_id"],
                "X-File-Name":     filename_encoded,
                "X-File-Type":     doc_meta["file_type"],
                "X-Docs-Remaining": str(doc_meta["docs_remaining"]),
                "X-Duplicate":      is_duplicate_str,
                # Allow frontend JS to read these custom headers
                "Access-Control-Expose-Headers": (
                    "X-Document-Id, X-File-Name, X-File-Type, X-Docs-Remaining, X-Duplicate"
                ),
            },
        )

    # ── Fallback JSON if no LLM ───────────────────────────────────────────
    remaining = doc_meta["docs_remaining"]
    is_dup = doc_meta.get("duplicate", False)
    message = (
        f"Document '{filename}' uploaded successfully."
        if not is_dup else
        f"Document '{filename}' already exists. Reusing original document."
    )
    return DocumentUploadResponse(
        document_id=doc_meta["document_id"],
        file_name=doc_meta["file_name"],
        file_type=doc_meta["file_type"],
        char_count=doc_meta["char_count"],
        upload_order=doc_meta["upload_order"],
        docs_remaining=remaining,
        message=message,
        duplicate=is_dup,
    )


# ── Save file message endpoint ────────────────────────────────────────────────
@router.post(
    "/documents/message/{conversation_id}",
    tags=["Documents"],
    summary="Persist a file-upload event as a chat message for history",
)
async def save_file_message(
    conversation_id: str,
    body: FileMessageRequest,
    user: ClerkUser = Depends(get_current_user),
):
    if _document_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document service not available.",
        )
    try:
        message_id = _document_service.save_file_message(
            conversation_id=conversation_id,
            role=body.role,
            content=body.content,
            file_name=body.file_name,
            metadata={"document_id": body.document_id},
        )
        return {"message_id": message_id, "status": "saved"}
    except Exception as exc:
        logger.error(
            f"❌ save_file_message failed | conv={conversation_id} | {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file message: {exc}",
        )


# ── Save summary message endpoint ────────────────────────────────────────────
class SummaryMessageRequest(BaseModel):
    content: str
    document_id: Optional[str] = None


@router.post(
    "/documents/summary-message/{conversation_id}",
    tags=["Documents"],
    summary="Persist an AI document summary as an assistant message for history",
)
async def save_summary_message(
    conversation_id: str,
    body: SummaryMessageRequest,
    user: ClerkUser = Depends(get_current_user),
):
    """
    Called by frontend after a document upload + summary generation.
    Saves the AI summary as an assistant message so it reappears
    correctly when the conversation is loaded from history (after refresh).
    """
    if _document_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document service not available.",
        )
    try:
        message_id = _document_service.save_summary_message(
            conversation_id=conversation_id,
            content=body.content,
            document_id=body.document_id,
        )
        return {"message_id": message_id, "status": "saved"}
    except Exception as exc:
        logger.error(
            f"❌ save_summary_message failed | conv={conversation_id} | {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save summary message: {exc}",
        )


# ── Session status endpoint ───────────────────────────────────────────────────
@router.get(
    "/documents/session/{conversation_id}",
    response_model=SessionStatusResponse,
    tags=["Documents"],
    summary="Get document session status for a conversation",
)
async def get_session_status(
    conversation_id: str,
    user: ClerkUser = Depends(get_current_user),
):
    if _document_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document service not available.",
        )

    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id)
    
    # 1. Get Quota Stats (User-wide)
    quota = _document_service.get_quota_session(internal_user_id)
    
    # 2. Get Document List (Conversation-specific)
    conv_session = _document_service.get_or_create_session(conversation_id)
    
    from config import settings
    from datetime import datetime
    
    session_start = quota.get("session_start", time.time())
    reset_time = session_start + settings.DOC_SESSION_TTL_SECONDS
    reset_at_iso = datetime.utcfromtimestamp(reset_time).isoformat() + "Z"

    return SessionStatusResponse(
        conversation_id=conversation_id,
        doc_count=quota.get("doc_count", 0),
        turn_count=quota.get("turn_count", 0),
        token_count=quota.get("token_count", 0),
        docs_remaining=max(0, settings.DOC_MAX_PER_SESSION - quota.get("doc_count", 0)),
        turns_remaining=max(0, settings.DOC_MAX_TURNS_PER_SESSION - quota.get("turn_count", 0)),
        tokens_remaining=max(0, settings.DOC_MAX_TOKENS_PER_SESSION - quota.get("token_count", 0)),
        has_documents=_document_service.has_documents(conversation_id),
        session_active=True,
        reset_at=reset_at_iso,
        docs=conv_session.get("docs", []),
    )


# ── View/Download endpoint ───────────────────────────────────────────────────
@router.get(
    "/documents/view/{document_id}",
    tags=["Documents"],
    summary="View or download the original uploaded document",
)
async def get_document_view(
    document_id: str,
    user: ClerkUser = Depends(get_current_user),
):
    if _document_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document service not available.",
        )

    result = _document_service.get_document_binary(document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or could not be retrieved from storage.",
        )

    file_bytes, filename, content_type = result

    from fastapi.responses import Response
    import urllib.parse

    # UTF-8 encoded filename for Content-Disposition (handles non-ASCII chars)
    filename_encoded = urllib.parse.quote(filename)
    
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename_encoded}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )