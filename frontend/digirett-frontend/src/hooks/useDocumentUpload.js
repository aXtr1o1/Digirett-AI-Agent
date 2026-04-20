import { useState, useCallback } from "react";
import { DEFAULT_USER_ID } from "../utils/constants";

const BASE_URL = "http://localhost:8000";

/**
 * useDocumentUpload
 *
 * Handles document upload and session status for Digirett.
 *
 * NOTE: The backend hardcodes DEFAULT_USER_ID for all requests.
 * The userId param is kept for API compatibility but the backend
 * validates against its own DEFAULT_USER_ID constant regardless.
 */
const useDocumentUpload = (conversationId, userId, addMessage) => {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [sessionStatus, setSessionStatus] = useState(null);
  const [uploadedDocs, setUploadedDocs] = useState([]);

  // ── Fetch session status ──────────────────────────────────────────────────
  const fetchSessionStatus = useCallback(async (convId) => {
    const id = convId || conversationId;
    if (!id) return;

    try {
      const res = await fetch(`${BASE_URL}/api/v1/documents/session/${id}`);
      if (!res.ok) return;
      const data = await res.json();
      setSessionStatus(data);
    } catch (err) {
      console.error("[useDocumentUpload] fetchSessionStatus error:", err);
    }
  }, [conversationId]);

  // ── Upload a document ─────────────────────────────────────────────────────
  const uploadDocument = useCallback(async (file, convId) => {
    const id = convId || conversationId;

    // ── Client-side file type guard ───────────────────────────────────────
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["pdf", "docx", "doc"].includes(ext)) {
      setUploadError("Only PDF or Word documents (.pdf, .docx, .doc) are accepted.");
      return null;
    }

    // ── Client-side file size guard (20MB) ────────────────────────────────
    if (file.size > 20 * 1024 * 1024) {
      setUploadError("File is too large. Maximum size is 20 MB.");
      return null;
    }

    // ── Must have a conversation ID ───────────────────────────────────────
    // NOTE: removed the !userId guard — the backend uses its own DEFAULT_USER_ID
    // and does not depend on the userId passed from the frontend being valid.
    if (!id) {
      setUploadError("No active conversation. Please try again.");
      return null;
    }

    setIsUploading(true);
    setUploadError(null);

    try {
      const form = new FormData();
      form.append("conversation_id", id);
      // Use DEFAULT_USER_ID — backend validates against this exact value
      form.append("user_id", userId || DEFAULT_USER_ID);
      form.append("file", file);
      // ⚠️ Do NOT set Content-Type — browser sets it with the multipart boundary

      const res = await fetch(`${BASE_URL}/api/v1/documents/upload`, {
        method: "POST",
        body: form,
      });

      const data = await res.json();

      if (!res.ok) {
        setUploadError(data.detail ?? data.message ?? "Upload failed.");
        return null;
      }
      
      if (addMessage) {
        addMessage({
          id: Date.now(),
          type: "file",
          fileName: data.file_name || file.name,
          role: "user",
        });
      }

      setUploadedDocs(prev => [
        ...prev,
        {
          document_id:  data.document_id,
          file_name:    data.file_name,
          upload_order: data.upload_order,
        },
      ]);

      await fetchSessionStatus(id);
      return data;

    } catch (err) {
      console.error("[useDocumentUpload] uploadDocument error:", err);
      setUploadError("Network error. Please try again.");
      return null;
    } finally {
      setIsUploading(false);
    }
  }, [conversationId, userId, fetchSessionStatus]);

  // ── Helpers ───────────────────────────────────────────────────────────────
  const clearUploadError = useCallback(() => setUploadError(null), []);

  const isUploadDisabled =
    isUploading ||
    (sessionStatus !== null && sessionStatus.docs_remaining === 0);

  const isChatDisabled =
    sessionStatus !== null && sessionStatus.turns_remaining === 0;

  return {
    uploadDocument,
    fetchSessionStatus,
    sessionStatus,
    uploadedDocs,
    isUploading,
    uploadError,
    clearUploadError,
    isUploadDisabled,
    isChatDisabled,
  };
};

export default useDocumentUpload;