import api from './api';
import { API_ENDPOINTS } from '../utils/constants';

/**
 * Conversation Service
 * Handles all conversation-related API calls
 */
const conversationService = {
  /**
   * Create a new conversation
   * POST /conversations
   */
  createNewConversation: async () => {
    try {
      const response = await api.post(API_ENDPOINTS.CONVERSATIONS.CREATE);
      return response.data;
    } catch (error) {
      console.error('Error creating conversation:', error);
      throw error;
    }
  },

  /**
   * Get list of all conversations for the current user
   * GET /conversations
   */
  listConversations: async () => {
    try {
      const response = await api.get(API_ENDPOINTS.CONVERSATIONS.LIST);
      return response.data;
    } catch (error) {
      console.error('Error fetching conversations:', error);
      throw error;
    }
  },

  /**
   * Get all messages from a specific conversation
   * GET /conversations/{conversation_id}/messages
   */
  getConversationMessages: async (conversationId) => {
    try {
      const response = await api.get(
        API_ENDPOINTS.CONVERSATIONS.GET_MESSAGES(conversationId)
      );
      return response.data;
    } catch (error) {
      console.error('Error fetching conversation messages:', error);
      throw error;
    }
  },

  /**
   * Delete a conversation (if backend supports it)
   * DELETE /conversations/{conversation_id}
   */
  deleteConversation: async (conversationId) => {
    try {
      const response = await api.delete(`/conversations/${conversationId}`);
      return response.data;
    } catch (error) {
      console.error('Error deleting conversation:', error);
      throw error;
    }
  },
};

export default conversationService;
