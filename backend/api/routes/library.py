import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status, File, Form, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.auth import ClerkUser, get_current_user
from schemas.requests import LibraryNoteUpdateRequest
from schemas.responses import LibraryDocumentResponse

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

_library_service = None
_user_service = None

def set_services(library_service, user_service) -> None:
    global _library_service, _user_service
    _library_service = library_service
    _user_service = user_service

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
    user: ClerkUser = Depends(get_current_user),
):
    if _library_service is None or _user_service is None:
         raise HTTPException(
             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
             detail="Library service not available.",
         )

    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("pdf", "docx", "doc"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: .{ext}. Please upload a PDF or DOCX file.",
        )

    try:
        file_bytes = await file.read()
        saved = _library_service.save_document(
            user_id=internal_user_id,
            file_name=filename,
            file_type=ext,
            file_bytes=file_bytes,
            note=note
        )
        if not saved:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save document to library."
            )
        return LibraryDocumentResponse(**saved)
    except Exception as exc:
        logger.error(f"Error uploading to library: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
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
    user: ClerkUser = Depends(get_current_user),
):
    if _library_service is None or _user_service is None:
         raise HTTPException(
             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
             detail="Library service not available.",
         )

    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    try:
        documents = _library_service.get_library_documents(internal_user_id)
        return [LibraryDocumentResponse(**d) for d in documents]
    except Exception as exc:
        logger.error(f"Error getting library documents: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )

@router.delete(
    "/library/documents/{document_id}",
    tags=["Library"],
    summary="Remove a document from the library",
)
@limiter.limit("60/minute")
async def delete_library_document(
    request: Request,
    document_id: str,
    user: ClerkUser = Depends(get_current_user),
):
    if _library_service is None or _user_service is None:
         raise HTTPException(
             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
             detail="Library service not available.",
         )

    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    try:
        success = _library_service.delete_library_document(document_id, internal_user_id)
        return {"success": success}
    except Exception as exc:
        logger.error(f"Error deleting from library: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
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
    user: ClerkUser = Depends(get_current_user),
):
    if _library_service is None or _user_service is None:
         raise HTTPException(
             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
             detail="Library service not available.",
         )

    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    try:
        updated = _library_service.update_library_document_note(document_id, internal_user_id, body.note)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Library document not found."
            )
        return LibraryDocumentResponse(**updated)
    except Exception as exc:
        logger.error(f"Error updating library document note: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )

@router.get(
    "/library/documents/{document_id}/view",
    tags=["Library"],
    summary="View or download a document from the library",
)
async def get_library_document_view(
    document_id: str,
    user: ClerkUser = Depends(get_current_user),
):
    if _library_service is None or _user_service is None:
         raise HTTPException(
             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
             detail="Library service not available.",
         )

    internal_user_id = _user_service.get_user_id_from_clerk_id(user.clerk_user_id, email=user.email)
    if not internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in database.",
        )

    # Get user role from the database to check for support privileges
    try:
        user_data = _user_service._supabase.table("users").select("role").eq("user_id", internal_user_id).single().execute()
        user_role = user_data.data.get("role", "user") if user_data.data else "user"
    except Exception:
        user_role = "user"

    is_privileged = user_role in ("lawyer", "admin", "system_admin")

    try:
        result = _library_service.get_library_document_binary(document_id, internal_user_id, is_privileged=is_privileged)
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
    except Exception as exc:
        logger.error(f"Error viewing library document: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )
