import { useState, useCallback, useEffect } from "react";
import conversationService from "../services/conversationService";

const useConversations = () => {
  const [conversations, setConversations] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [currentConversationId, setCurrentConversationId] = useState(null);

  /**
   * Load all conversations for the default user
   * GET /conversations/user/{user_id}
   */
  const loadConversations = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await conversationService.listConversations();
      const list = Array.isArray(data) ? data : [];
      setConversations(list);
    } catch (err) {
      setError(err.message || "Failed to load conversations");
      console.error("Error loading conversations:", err);
    } finally {
      setIsLoading(false);
    }
  }, [currentConversationId]);

  /**
   * Create a new conversation
   * POST /conversations
   */
  const createConversation = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const newConversation = await conversationService.createNewConversation();
      setConversations((prev) => [newConversation, ...prev]);
      setCurrentConversationId(newConversation.conversation_id);
      return newConversation;
    } catch (err) {
      setError(err.message || "Failed to create conversation");
      console.error("Error creating conversation:", err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Select a conversation by ID (sidebar click)
   */
  const selectConversation = useCallback((conversationId) => {
    setCurrentConversationId(conversationId);
  }, []);

  /**
   * Delete a conversation
   * DELETE /conversations/{conversation_id}
   * Removes from sidebar immediately (optimistic) — never blocks user
   */
  const deleteConversation = useCallback(
    async (conversationId) => {
      // ── Optimistic remove from UI first ──
      setConversations((prev) =>
        prev.filter((conv) => conv.conversation_id !== conversationId)
      );

      // If the deleted one was selected, select the next available
      if (currentConversationId === conversationId) {
        const remaining = conversations.filter(
          (conv) => conv.conversation_id !== conversationId
        );
        if (remaining.length > 0) {
          setCurrentConversationId(remaining[0].conversation_id);
        } else {
          setCurrentConversationId(null);
        }
      }

      // ── Then call backend (errors are swallowed — UI already updated) ──
      try {
        await conversationService.deleteConversation(conversationId);
      } catch (err) {
        // Don't re-add to UI or show error — just log
        console.error("Backend delete failed but UI already updated:", err);
      }
    },
    [conversations, currentConversationId]
  );

  /**
   * Get the current conversation object
   */
  const getCurrentConversation = useCallback(() => {
    return conversations.find(
      (conv) => conv.conversation_id === currentConversationId
    );
  }, [conversations, currentConversationId]);

  /**
   * Called by ChatPage when backend auto-creates a conversation
   * during /chat/stream (conversation_id was null)
   */
  const handleAutoCreatedConversation = useCallback(
    (newConversationId) => {
      setCurrentConversationId(newConversationId);
      // Reload sidebar to show the new conversation with its title
      conversationService.listConversations().then((data) => {
        const list = Array.isArray(data) ? data : [];
        setConversations(list);
      }).catch(() => {});
    },
    []
  );

  // Load on mount
  useEffect(() => {
    loadConversations();
  }, []);

  return {
    conversations,
    isLoading,
    error,
    currentConversationId,
    setCurrentConversationId,
    loadConversations,
    createConversation,
    selectConversation,
    deleteConversation,
    getCurrentConversation,
    handleAutoCreatedConversation,
  };
};

export default useConversations;