import { useState, useCallback, useEffect } from 'react';
import conversationService from '../services/conversationService';

/**
 * Custom hook for managing conversations
 */
const useConversations = () => {
  const [conversations, setConversations] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [currentConversationId, setCurrentConversationId] = useState(null);

  /**
   * Load all conversations
   */
  const loadConversations = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await conversationService.listConversations();
      const conversationList = response.conversations || response || [];
      setConversations(conversationList);

      // Set current conversation if none selected
      if (!currentConversationId && conversationList.length > 0) {
        setCurrentConversationId(conversationList[0].id || conversationList[0].conversation_id);
      }
    } catch (err) {
      setError(err.message || 'Failed to load conversations');
      console.error('Error loading conversations:', err);
    } finally {
      setIsLoading(false);
    }
  }, [currentConversationId]);

  /**
   * Create a new conversation
   */
  const createConversation = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await conversationService.createNewConversation();
      const newConversation = response.conversation || response;
      
      setConversations(prev => [newConversation, ...prev]);
      setCurrentConversationId(newConversation.id || newConversation.conversation_id);
      
      return newConversation;
    } catch (err) {
      setError(err.message || 'Failed to create conversation');
      console.error('Error creating conversation:', err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Select a conversation
   */
  const selectConversation = useCallback((conversationId) => {
    setCurrentConversationId(conversationId);
  }, []);

  /**
   * Delete a conversation
   */
  const deleteConversation = useCallback(async (conversationId) => {
    try {
      await conversationService.deleteConversation(conversationId);
      setConversations(prev => prev.filter(conv => 
        (conv.id || conv.conversation_id) !== conversationId
      ));

      // If deleted conversation was selected, select another one
      if (currentConversationId === conversationId) {
        const remaining = conversations.filter(conv => 
          (conv.id || conv.conversation_id) !== conversationId
        );
        if (remaining.length > 0) {
          setCurrentConversationId(remaining[0].id || remaining[0].conversation_id);
        } else {
          setCurrentConversationId(null);
        }
      }
    } catch (err) {
      console.error('Error deleting conversation:', err);
      throw err;
    }
  }, [conversations, currentConversationId]);

  /**
   * Get current conversation object
   */
  const getCurrentConversation = useCallback(() => {
    return conversations.find(conv => 
      (conv.id || conv.conversation_id) === currentConversationId
    );
  }, [conversations, currentConversationId]);

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, []);

  return {
    conversations,
    isLoading,
    error,
    currentConversationId,
    loadConversations,
    createConversation,
    selectConversation,
    deleteConversation,
    getCurrentConversation,
  };
};

export default useConversations;
