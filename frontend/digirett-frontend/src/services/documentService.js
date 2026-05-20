import api from "./api";
import { API_ENDPOINTS, API_BASE_URL } from "../utils/constants";

const documentService = {
  /**
   * Upload a document and stream the summary response.
   * Uses fetch directly to handle the ReadableStream from the backend.
   */
  uploadDocumentStream: async (file, conversationId, onToken) => {
    const formData = new FormData();
    formData.append("conversation_id", conversationId);
    formData.append("file", file);

    const token = await window.Clerk?.session?.getToken();
    const headers = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const response = await fetch(`${API_BASE_URL}/api/v1${API_ENDPOINTS.DOCUMENTS.UPLOAD}`, {
      method: "POST",
      headers,
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || errorData.message || "Upload failed");
    }

    // Extract metadata from headers
    const rawFileName = response.headers.get("X-File-Name");
    const meta = {
      documentId: response.headers.get("X-Document-Id"),
      fileName: rawFileName ? decodeURIComponent(rawFileName) : file.name,
      fileType: response.headers.get("X-File-Type"),
      docsRemaining: response.headers.get("X-Docs-Remaining"),
    };

    // Consume the stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let fullSummary = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      fullSummary += chunk;
      if (onToken) onToken(chunk);
    }

    return { ...meta, summaryText: fullSummary.trim() };
  },

  /**
   * Get document session status for a conversation
   */
  getSessionStatus: async (conversationId) => {
    const response = await api.get(API_ENDPOINTS.DOCUMENTS.SESSION(conversationId));
    return response.data;
  },

  /**
   * Persist a file-upload event as a chat message
   */
  saveFileMessage: async (conversationId, data) => {
    const response = await api.post(API_ENDPOINTS.DOCUMENTS.SAVE_MESSAGE(conversationId), data);
    return response.data;
  },

  /**
   * Persist an AI document summary as an assistant message
   */
  saveSummaryMessage: async (conversationId, data) => {
    const response = await api.post(API_ENDPOINTS.DOCUMENTS.SAVE_SUMMARY(conversationId), data);
    return response.data;
  },

  /**
   * Get URL for viewing/downloading a document
   */
  getDocumentViewUrl: (documentId) => {
    return `${API_BASE_URL}/api/v1${API_ENDPOINTS.DOCUMENTS.VIEW(documentId)}`;
  },
};

export default documentService;
