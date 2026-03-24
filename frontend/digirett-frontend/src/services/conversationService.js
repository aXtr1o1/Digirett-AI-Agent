import api from "./api";
import { API_ENDPOINTS, DEFAULT_USER_ID } from "../utils/constants";

const conversationService = {

  createNewConversation: async (title = null) => {
    try {
      const response = await api.post(API_ENDPOINTS.CONVERSATIONS.CREATE, {
        user_id: DEFAULT_USER_ID,
        ...(title ? { title } : {}),
      });
      console.log("[conversationService] createNewConversation response:", response.data);
      return response.data;
    } catch (error) {
      console.error("[conversationService] createNewConversation error:", error);
      throw error;
    }
  },

  listConversations: async () => {
    try {
      const response = await api.get(
        API_ENDPOINTS.CONVERSATIONS.LIST(DEFAULT_USER_ID)
      );
      const data = response.data;
      console.log("[conversationService] listConversations raw response:", data);

      if (Array.isArray(data)) return data;
      if (data && Array.isArray(data.conversations)) return data.conversations;
      return [];
    } catch (error) {
      console.error("[conversationService] listConversations error:", error);
      throw error;
    }
  },

  getConversationWithMessages: async (conversationId) => {
    try {
      const response = await api.get(
        API_ENDPOINTS.CONVERSATIONS.GET(conversationId)
      );
      const data = response.data;
      console.log("[conversationService] getConversationWithMessages raw:", JSON.stringify(data, null, 2));

      // Handle all possible shapes the backend might return
      if (Array.isArray(data)) {
        console.log("[conversationService] shape: direct array, length:", data.length);
        return { conversation: null, messages: data };
      }
      if (data && Array.isArray(data.messages)) {
        console.log("[conversationService] shape: {messages:[]}, length:", data.messages.length);
        return data;
      }
      // Maybe messages are nested under conversation?
      if (data && data.conversation && Array.isArray(data.conversation.messages)) {
        console.log("[conversationService] shape: {conversation:{messages:[]}}, length:", data.conversation.messages.length);
        return { conversation: data.conversation, messages: data.conversation.messages };
      }
      console.warn("[conversationService] unknown shape, keys:", Object.keys(data || {}));
      return { conversation: null, messages: [] };
    } catch (error) {
      console.error("[conversationService] getConversationWithMessages error:", error);
      throw error;
    }
  },

  deleteConversation: async (conversationId) => {
    // Guard: never send undefined to backend
    if (!conversationId || conversationId === "undefined") {
      console.warn("[conversationService] deleteConversation called with invalid ID:", conversationId);
      return { message: "Invalid ID — skipped" };
    }
    try {
      const response = await api.delete(
        API_ENDPOINTS.CONVERSATIONS.DELETE(conversationId)
      );
      console.log("[conversationService] deleteConversation response:", response.data);
      return response.data;
    } catch (error) {
      if (error.response && (error.response.status === 404 || error.response.status === 500)) {
        console.warn("[conversationService] delete returned", error.response.status, "- treating as success");
        return { message: "Removed" };
      }
      console.error("[conversationService] deleteConversation error:", error);
      throw error;
    }
  },
};

export default conversationService;