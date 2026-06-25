// frontend/digirett-frontend/src/services/libraryService.js
import api from "./api";
import { API_ENDPOINTS } from "../utils/constants";

// In-memory cache of saved message IDs to support synchronous checks in the UI (e.g. Message.jsx bookmark icon)
let savedMessageIds = new Set();
let isCacheLoaded = false;

const libraryService = {
  /**
   * Pre-load/fetch the saved message IDs into cache.
   * Typically called on app initialization or ChatPage load.
   */
  loadCache: async () => {
    try {
      const response = await api.get(API_ENDPOINTS.LIBRARY.LIST);
      const messages = response.data || [];
      savedMessageIds = new Set(messages.map((m) => m.message_id));
      isCacheLoaded = true;
      return messages;
    } catch (error) {
      console.error("[libraryService] Error loading cache:", error);
      return [];
    }
  },

  /**
   * Get all saved messages.
   * @returns {Promise<Array>} List of saved messages.
   */
  getSavedMessages: async () => {
    try {
      const response = await api.get(API_ENDPOINTS.LIBRARY.LIST);
      const messages = response.data || [];
      
      // Update cache in case it changed
      savedMessageIds = new Set(messages.map((m) => m.message_id));
      isCacheLoaded = true;
      
      return messages;
    } catch (error) {
      console.error("[libraryService] Error reading saved messages:", error);
      return [];
    }
  },

  /**
   * Save a message to the library.
   * @param {Object} message - The message object containing message_id/id.
   */
  saveMessage: async (message) => {
    try {
      const msgId = message.message_id || message.id;
      if (!msgId) throw new Error("Message ID is required to save to library");

      const response = await api.post(API_ENDPOINTS.LIBRARY.SAVE, {
        message_id: msgId,
        note: ""
      });

      // Update in-memory cache
      savedMessageIds.add(msgId);
      
      // Dispatch a custom event to notify listeners of changes
      window.dispatchEvent(new Event("digirett_library_updated"));
      
      return response.data;
    } catch (error) {
      console.error("[libraryService] Error saving message:", error);
      throw error;
    }
  },

  /**
   * Remove a message from the library.
   * @param {string} messageId - The ID of the message to remove.
   */
  unsaveMessage: async (messageId) => {
    try {
      if (!messageId) throw new Error("Message ID is required to unsave");

      await api.delete(API_ENDPOINTS.LIBRARY.DELETE(messageId));
      
      // Update in-memory cache
      savedMessageIds.delete(messageId);
      
      // Dispatch event
      window.dispatchEvent(new Event("digirett_library_updated"));
      
      return true;
    } catch (error) {
      console.error("[libraryService] Error unsaving message:", error);
      throw error;
    }
  },

  /**
   * Check if a message is saved. (Synchronous, relies on loaded cache)
   * @param {string} messageId - The message ID to check.
   * @returns {boolean} True if saved.
   */
  isMessageSaved: (messageId) => {
    if (!messageId) return false;
    return savedMessageIds.has(messageId);
  },

  /**
   * Check if the cache has been loaded from backend.
   * @returns {boolean}
   */
  isCacheLoaded: () => {
    return isCacheLoaded;
  },

  /**
   * Update the user notes/annotations for a saved message.
   * @param {string} messageId - The message ID.
   * @param {string} note - The updated annotation string.
   */
  updateMessageNote: async (messageId, note) => {
    try {
      if (!messageId) throw new Error("Message ID is required to update note");

      const response = await api.patch(API_ENDPOINTS.LIBRARY.UPDATE_NOTE(messageId), {
        note
      });
      
      // Dispatch event
      window.dispatchEvent(new Event("digirett_library_updated"));
      
      return response.data;
    } catch (error) {
      console.error("[libraryService] Error updating message note:", error);
      throw error;
    }
  },
};

export default libraryService;
