import { useState, useCallback } from "react";
import documentService from "../services/documentService";

/**
 * useDocumentUpload
 *
 * Handles document upload and session status for Digirett.
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
      const data = await documentService.getSessionStatus(id);
      setSessionStatus(data);
    } catch (err) {
      console.error("[useDocumentUpload] fetchSessionStatus error:", err);
    }
  }, [conversationId]);

  // ── Upload a document ─────────────────────────────────────────────────────
  const uploadDocument = useCallback(async (file, convId, skipSummary = false) => {
    const id = convId || conversationId;

    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["pdf", "docx", "doc"].includes(ext)) {
      setUploadError("Only PDF or Word documents (.pdf, .docx, .doc) are accepted.");
      return null;
    }

    if (file.size > 20 * 1024 * 1024) {
      setUploadError("File is too large. Maximum size is 20 MB.");
      return null;
    }

    if (!id) {
      setUploadError("No active conversation. Please try again.");
      return null;
    }

    setIsUploading(true);
    setUploadError(null);

    try {
      const result = await documentService.uploadDocumentStream(file, id);

      setUploadedDocs(prev => [...prev, { file_name: result.fileName, document_id: result.documentId }]);
      await fetchSessionStatus(id);

      return {
        file_name: result.fileName,
        document_id: result.documentId,
        summary_text: result.summaryText
      };

    } catch (err) {
      console.error("[useDocumentUpload] uploadDocument error:", err);
      setUploadError(err.message || "Network error. Please try again.");
      return null;
    } finally {
      setIsUploading(false);
    }
  }, [conversationId, fetchSessionStatus]);

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