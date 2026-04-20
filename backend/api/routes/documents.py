import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Injected from main.py via set_services() ─────────────────────────────────
_document_service = None


def set_services(document_service) -> None:
    global _document_service
    _document_service = document_service


# ── Response model ────────────────────────────────────────────────────────────
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
    """
    Upload a document for the current conversation session.

    Session limits (per 4-hour session):
      - Max 2 documents
      - Max 10 conversation turns

    The document text will be used to answer DOCQA and HYBRID queries.
    """
    if _document_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document service not available.",
        )

    # ── Validate file type ────────────────────────────────────────────────
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("pdf", "docx", "doc"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type: .{ext}. "
                "Please upload a PDF or DOCX file."
            ),
        )

    # ── Validate file size (20MB max) ─────────────────────────────────────
    MAX_SIZE = 20 * 1024 * 1024  # 20MB
    file_bytes = await file.read()
    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is 20MB.",
        )

    # ── Check doc limit before parsing (fail fast) ────────────────────────
    allowed, docs_remaining = _document_service.check_doc_limit(conversation_id)
    if not allowed:
        session = _document_service.get_or_create_session(conversation_id)
        import time
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

    # ── Store document ─────────────────────────────────────────────────────
    try:
        doc_meta = _document_service.store_document(
            conversation_id=conversation_id,
            user_id=user_id,
            file_bytes=file_bytes,
            filename=filename,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(
            f"❌ Document upload failed | conv={conversation_id} | {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {exc}",
        )

    remaining = doc_meta["docs_remaining"]
    message = (
        f"Document '{filename}' uploaded and parsed successfully. "
        f"{'1 more document' if remaining == 1 else 'No more documents'} "
        f"can be uploaded this session."
        if remaining > 0
        else f"Document '{filename}' uploaded. You have reached the 2-document limit for this session."
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
    """
    Returns:
      - How many documents have been uploaded this session
      - How many conversation turns have been used
      - Whether more uploads are allowed
    """
    if _document_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document service not available.",
        )

    session = _document_service.get_or_create_session(conversation_id)
    doc_count   = session.get("doc_count", 0)
    turn_count  = session.get("turn_count", 0)

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