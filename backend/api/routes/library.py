import logging
import urllib.parse
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import settings
from core.auth import ClerkUser, get_current_user
from schemas.requests import LibraryNoteUpdateRequest
from schemas.responses import LibraryDeleteResponse, LibraryDocumentResponse
from services.library_service import LibraryService
from services.user_service import UserService

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

def get_library_service(request: Request) -> LibraryService:
    svc = getattr(request.app.state, "library_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LibraryService is not initialized on application state.",
        )
    return svc


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

_ALLOWED_EXTENSIONS = {"pdf", "docx", "doc"}
_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/x-pdf",
    "binary/octet-stream",
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
        if not (file_bytes.startswith(b"PK\x03\x04") or file_bytes.startswith(b"\xd0\xcf\x11\xe0")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match DOCX/DOC signature.",
            )

    return ext

@router.post(
    "/library/documents/upload",
    response_model=LibraryDocumentResponse,
    tags=["Library"],
    summary="Upload a new document directly to the library",
)
@limiter.limit("60/minute")
async def upload_to_library(
    request: Request,
    file: UploadFile = File(...),
    note: Optional[str] = Form(""),
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    library_service: LibraryService = Depends(get_library_service),
):
    _, internal_user_id = user_context
    filename = file.filename or ""

    file_bytes = await file.read()

    # 1. 3-Layer File Validation
    ext = _validate_file_security(filename, file.content_type or "", file_bytes)

    # 2. File Size Limit Check
    if len(file_bytes) > settings.MAX_DOCUMENT_SIZE:
        max_mb = settings.MAX_DOCUMENT_SIZE // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {max_mb}MB.",
        )

    try:
        saved = library_service.save_document(
            user_id=internal_user_id,
            file_name=filename,
            file_type=ext,
            file_bytes=file_bytes,
            note=note,
        )
        if not saved:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save document to library.",
            )
        return LibraryDocumentResponse(**saved)
    except HTTPException:
        raise
    except ValueError as val_exc:
        logger.warning(f" Library upload validation failed: {val_exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_exc),
        )
    except Exception as exc:
        logger.exception(f" Error uploading to library: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload document to library.",
        )


@router.get(
    "/library/documents",
    response_model=List[LibraryDocumentResponse],
    tags=["Library"],
    summary="Get all saved documents in user library",
)
@limiter.limit("60/minute")
async def get_library_documents(
    request: Request,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    library_service: LibraryService = Depends(get_library_service),
):
    _, internal_user_id = user_context
    try:
        documents = library_service.get_library_documents(internal_user_id)
        return [LibraryDocumentResponse(**d) for d in documents]
    except Exception as exc:
        logger.exception(f" Error getting library documents: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve library documents.",
        )


@router.delete(
    "/library/documents/{document_id}",
    response_model=LibraryDeleteResponse,
    tags=["Library"],
    summary="Remove a document from the library",
)
@limiter.limit("60/minute")
async def delete_library_document(
    request: Request,
    document_id: str,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    library_service: LibraryService = Depends(get_library_service),
):
    _, internal_user_id = user_context
    try:
        success = library_service.delete_library_document(document_id, internal_user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Library document not found or deletion failed.",
            )
        return LibraryDeleteResponse(
            success=True,
            message="Document successfully removed from library.",
            document_id=document_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f" Error deleting library document {document_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document from library.",
        )


@router.patch(
    "/library/documents/{document_id}",
    response_model=LibraryDocumentResponse,
    tags=["Library"],
    summary="Update notes/annotations for a saved document",
)
@limiter.limit("60/minute")
async def update_library_document_note(
    request: Request,
    document_id: str,
    body: LibraryNoteUpdateRequest,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    library_service: LibraryService = Depends(get_library_service),
):
    _, internal_user_id = user_context
    try:
        updated = library_service.update_library_document_note(document_id, internal_user_id, body.note)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Library document not found.",
            )
        return LibraryDocumentResponse(**updated)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f" Error updating library document note {document_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update document note.",
        )


@router.get(
    "/library/documents/{document_id}/view",
    tags=["Library"],
    summary="View or download a document from the library",
)
async def get_library_document_view(
    document_id: str,
    user_context: Tuple[ClerkUser, str] = Depends(get_current_internal_user),
    library_service: LibraryService = Depends(get_library_service),
    user_service: UserService = Depends(get_user_service),
):
    user, internal_user_id = user_context

    # Fetch user role via UserService cleanly without accessing private _supabase
    user_role = user_service.get_user_role(user.clerk_user_id) or user.role
    is_privileged = user_role in ("lawyer", "admin", "system_admin")

    try:
        result = library_service.get_library_document_binary(
            document_id, internal_user_id, is_privileged=is_privileged
        )
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
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f" Error viewing library document {document_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve library document binary.",
        )