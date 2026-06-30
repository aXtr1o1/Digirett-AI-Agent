// frontend/digirett-frontend/src/services/libraryService.js
import api from "./api";
import { API_ENDPOINTS } from "../utils/constants";

const libraryService = {
  /**
   * Get all saved library documents.
   * @returns {Promise<Array>} List of library documents.
   */
  getSavedMessages: async () => {
    try {
      const response = await api.get(API_ENDPOINTS.LIBRARY.LIST);
      return response.data || [];
    } catch (error) {
      console.error("[libraryService] Error reading library documents:", error);
      return [];
    }
  },

  /**
   * Upload a new document to the library.
   * @param {File} file - The binary file object.
   * @param {string} note - Optional initial note.
   */
  uploadDocument: async (file, note = "") => {
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (note) {
        formData.append("note", note);
      }

      const response = await api.post(API_ENDPOINTS.LIBRARY.UPLOAD, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      // Dispatch a custom event to notify listeners of changes
      window.dispatchEvent(new Event("digirett_library_updated"));
      
      return response.data;
    } catch (error) {
      console.error("[libraryService] Error uploading document:", error);
      throw error;
    }
  },

  /**
   * Remove a document from the library.
   * @param {string} documentId - The ID of the document to remove.
   */
  unsaveMessage: async (documentId) => {
    try {
      if (!documentId) throw new Error("Document ID is required to delete");

      await api.delete(API_ENDPOINTS.LIBRARY.DELETE(documentId));
      
      // Dispatch event
      window.dispatchEvent(new Event("digirett_library_updated"));
      
      return true;
    } catch (error) {
      console.error("[libraryService] Error deleting document:", error);
      throw error;
    }
  },

  /**
   * Update the user notes/annotations for a library document.
   * @param {string} documentId - The document ID.
   * @param {string} note - The updated annotation string.
   */
  updateMessageNote: async (documentId, note) => {
    try {
      if (!documentId) throw new Error("Document ID is required to update note");

      const response = await api.patch(API_ENDPOINTS.LIBRARY.UPDATE_NOTE(documentId), {
        note
      });
      
      // Dispatch event
      window.dispatchEvent(new Event("digirett_library_updated"));
      
      return response.data;
    } catch (error) {
      console.error("[libraryService] Error updating document note:", error);
      throw error;
    }
  },
};

export default libraryService;
