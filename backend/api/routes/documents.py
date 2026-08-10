import asyncio
import logging
import re
import time
import urllib.parse
from datetime import datetime
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from config import settings
from core.auth import ClerkUser, get_current_user
from services.document_service import DocumentService
from services.llm_service import LLMService
from services.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter()

def get_document_service(request: Request) -> DocumentService:
    svc = getattr(request.app.state, "document_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DocumentService is not initialized on application state.",
        )
    return svc


def get_llm_service(request: Request) -> Optional[LLMService]:
    return getattr(request.app.state, "llm_service", None)


def get_user_service(request: Request) -> UserService:
    svc = getattr(request.app.state, "user_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UserService is not initialized on application state.",
        )
    return svc


def get_current_internal_user(
    user: ClerkUser = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> Tuple[ClerkUser, str]:
    """Resolves current authenticated user and internal database user_id."""
    internal_user_id = user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )
    return user, internal_user_id

from schemas.requests import FileMessageRequest, SummaryMessageRequest
from schemas.responses import DocumentUploadResponse, SessionStatusResponse


_ALLOWED_EXTENSIONS = {"pdf", "docx", "doc"}
_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/x-pdf",
    "binary/octet-stream",  # Fallback for raw byte uploads
}


def _validate_file_security(filename: str, content_type: str, file_bytes: bytes) -> str:
    """3-Layer Comprehensive Validation: Extension + MIME Type + Magic Byte Signatures."""
    # 1. Extension Check
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: .{ext}. Please upload a PDF or DOCX file.",
        )

    # 2. MIME Type Check
    if content_type and content_type.lower() not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid MIME type: '{content_type}'. Only PDF and DOCX documents are allowed.",
        )

    # 3. Magic Byte Signature Check
    if ext == "pdf":
        if not file_bytes.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match PDF signature.",
            )
    elif ext in ("docx", "doc"):
        # DOCX is a ZIP container starting with PK\x03\x04 header
        if not (file_bytes.startswith(b"PK\x03\x04") or file_bytes.startswith(b"\xd0\xcf\x11\xe0")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match DOCX/DOC signature.",
            )

    return ext

@router.post(
    "/documents/upload",
    tags=["Documents"],
    summary="Upload a document (PDF or DOCX) for document-grounded QA",
)
async def upload_document(
    conversation_id: str = Form(...),
    file: UploadFile = File(...),
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    document_service: DocumentService = Depends(get_document_service),
    llm_service: Optional[LLMService] = Depends(get_llm_service),
):
    user, internal_user_id = user_context
    filename = file.filename or ""

    file_bytes = await file.read()

    # 1. 3-Layer File Validation
    _validate_file_security(filename, file.content_type or "", file_bytes)

    # 2. Size Limit Check (Centralized setting)
    if len(file_bytes) > settings.MAX_DOCUMENT_SIZE:
        max_mb = settings.MAX_DOCUMENT_SIZE // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {max_mb}MB.",
        )

    # 3. Quota Check
    allowed, docs_remaining = document_service.check_doc_limit(internal_user_id, user_role=user.role)
    if not allowed:
        session = document_service.get_or_create_session(internal_user_id)
        elapsed = time.time() - session.get("session_start", time.time())
        remaining_hours = max(0, round((settings.DOC_SESSION_TTL_SECONDS - elapsed) / 3600, 1))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Document upload limit reached. "
                f"You can upload a maximum of {settings.DOC_MAX_PER_SESSION} documents per session. "
                f"Your session resets in approximately {remaining_hours} hour(s)."
            ),
        )

    try:
        doc_meta = document_service.store_document(
            conversation_id=conversation_id,
            user_id=internal_user_id,
            file_bytes=file_bytes,
            filename=filename,
            user_role=user.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error(f" Document upload failed | conv={conversation_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {exc}",
        )

    # Auto-summarize via streaming if LLMService or default summary is available
    cached_summary = doc_meta.get("summary")

    if cached_summary:
        async def stream_summary():
            words = cached_summary.split(" ")
            for i in range(0, len(words), 5):
                chunk = " ".join(words[i:i + 5]) + " "
                yield chunk
                await asyncio.sleep(0.01)

        logger.info(f"⚡ Streaming cached auto-summary | doc_id={doc_meta['document_id']}")
    else:
        # Generate summary using DocumentService text or LLMService
        doc_text = document_service.get_document_text(doc_meta["document_id"])
        
        async def stream_summary():
            accumulated = []
            if llm_service is not None:
                try:
                    async for token in llm_service.summarize_document_stream(doc_text):
                        accumulated.append(token)
                        yield token
                except Exception as exc:
                    logger.warning(f" Live summary stream failed, generating fallback | {exc}")

            if not accumulated:
                # If LLM stream produced nothing, stream clean extracted text without page headers
                raw_text = str(doc_text) if doc_text else ""
                clean_text = re.sub(r"\[Page \d+\]", "", raw_text).strip()
                clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
                
                full_content = clean_text if clean_text else "No extractable text content found."
                yield full_content
                accumulated.append(full_content)

            summary_str = "".join(accumulated).strip()
            if summary_str and doc_meta.get("file_hash"):
                document_service.update_file_summary(doc_meta["file_hash"], summary_str)

        logger.info(f" Streaming new auto-summary | doc_id={doc_meta['document_id']}")

    filename_encoded = urllib.parse.quote(filename)
    is_duplicate_str = "true" if doc_meta.get("duplicate", False) else "false"

    return StreamingResponse(
        stream_summary(),
        media_type="text/plain",
        headers={
            "X-Document-Id": doc_meta["document_id"],
            "X-File-Name": filename_encoded,
            "X-File-Type": doc_meta["file_type"],
            "X-Docs-Remaining": str(doc_meta["docs_remaining"]),
            "X-Duplicate": is_duplicate_str,
            "Access-Control-Expose-Headers": (
                "X-Document-Id, X-File-Name, X-File-Type, X-Docs-Remaining, X-Duplicate"
            ),
        },
    )


@router.post(
    "/documents/message/{conversation_id}",
    tags=["Documents"],
    summary="Persist a file-upload event as a chat message for history",
)
async def save_file_message(
    conversation_id: str,
    body: FileMessageRequest,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        message_id = document_service.save_file_message(
            conversation_id=conversation_id,
            role=body.role,
            content=body.content,
            file_name=body.file_name,
            metadata={"document_id": body.document_id},
        )
        return {"message_id": message_id, "status": "saved"}
    except Exception as exc:
        logger.error(f" save_file_message failed | conv={conversation_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file message: {exc}",
        )


@router.post(
    "/documents/summary-message/{conversation_id}",
    tags=["Documents"],
    summary="Persist an AI document summary as an assistant message for history",
)
async def save_summary_message(
    conversation_id: str,
    body: SummaryMessageRequest,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        message_id = document_service.save_summary_message(
            conversation_id=conversation_id,
            content=body.content,
            document_id=body.document_id,
        )
        return {"message_id": message_id, "status": "saved"}
    except Exception as exc:
        logger.error(f" save_summary_message failed | conv={conversation_id} | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save summary message: {exc}",
        )


@router.get(
    "/documents/session/{conversation_id}",
    response_model=SessionStatusResponse,
    tags=["Documents"],
    summary="Get document session status for a conversation",
)
async def get_session_status(
    conversation_id: str,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    document_service: DocumentService = Depends(get_document_service),
):
    _, internal_user_id = user_context

    quota = document_service.get_quota_session(internal_user_id)
    conv_session = document_service.get_or_create_session(conversation_id)

    session_start = quota.get("session_start", time.time()) if isinstance(quota, dict) else time.time()
    reset_time = session_start + settings.DOC_SESSION_TTL_SECONDS
    reset_at_iso = datetime.utcfromtimestamp(reset_time).isoformat() + "Z"

    doc_count = quota.get("doc_count", 0) if isinstance(quota, dict) else 0
    turn_count = quota.get("turn_count", 0) if isinstance(quota, dict) else 0
    token_count = quota.get("token_count", 0) if isinstance(quota, dict) else 0
    docs_list = conv_session.get("docs", []) if isinstance(conv_session, dict) else []

    return SessionStatusResponse(
        conversation_id=conversation_id,
        doc_count=doc_count,
        turn_count=turn_count,
        token_count=token_count,
        docs_remaining=max(0, settings.DOC_MAX_PER_SESSION - doc_count),
        turns_remaining=max(0, settings.DOC_MAX_TURNS_PER_SESSION - turn_count),
        tokens_remaining=max(0, settings.DOC_MAX_TOKENS_PER_SESSION - token_count),
        has_documents=document_service.has_documents(conversation_id),
        session_active=True,
        reset_at=reset_at_iso,
        docs=docs_list,
    )


@router.get(
    "/documents/view/{document_id}",
    tags=["Documents"],
    summary="View or download the original uploaded document",
)
async def get_document_view(
    document_id: str,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    document_service: DocumentService = Depends(get_document_service),
):
    user, internal_user_id = user_context

    # Explicit Defense-in-Depth Ownership Check
    owner_user_id = document_service.get_document_owner(document_id)
    if owner_user_id and owner_user_id != internal_user_id and user.role not in ["admin", "system_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view or download this document.",
        )

    result = document_service.get_document_binary(document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or could not be retrieved from storage.",
        )

    file_bytes, filename, content_type = result
    filename_encoded = urllib.parse.quote(filename)

    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename_encoded}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )