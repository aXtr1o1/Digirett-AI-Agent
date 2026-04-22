import { useState, useCallback } from "react";
import { DEFAULT_USER_ID, API_BASE_URL } from "../utils/constants";

/**
 * useDocumentUpload
 *
 * Handles document upload and session status for Digirett.
 *
 * NOTE: addMessage is intentionally NOT called here for the summary.
 * The summary text is returned to useChat, which controls message ordering:
 *   1. File bubble (user)
 *   2. Summary (assistant)  ← correct GPT-style order
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
      const res = await fetch(`${API_BASE_URL}/api/v1/documents/session/${id}`);
      if (!res.ok) return;
      const data = await res.json();
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
      const form = new FormData();
      form.append("conversation_id", id);
      form.append("user_id", userId || DEFAULT_USER_ID);
      form.append("file", file);

      const res = await fetch(`${API_BASE_URL}/api/v1/documents/upload`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const errData = await res.json();
        setUploadError(errData.detail ?? errData.message ?? "Upload failed.");
        return null;
      }

      // ✅ Read file_name and document_id from response header BEFORE consuming the stream
      const returnedFileName = res.headers.get("X-File-Name") || file.name;
      const documentId       = res.headers.get("X-Document-Id");

      // Stream the summary
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let summaryText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        summaryText += decoder.decode(value, { stream: true });
      }

      // ✅ NOTE: We do NOT call addMessage here anymore.
      // useChat controls the order: file bubble first, then summary below it.

      setUploadError(null);
      setUploadedDocs(prev => [...prev, { file_name: returnedFileName, document_id: documentId }]);
      await fetchSessionStatus(id);

      // ✅ Return everything needed by useChat
      return {
        file_name: returnedFileName,
        document_id: documentId,
        summary_text: summaryText.trim()
      };

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