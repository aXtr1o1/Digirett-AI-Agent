import { useState, useCallback, useEffect } from "react";
import conversationService from "../services/conversationService";

const useConversations = () => {
  const [conversations, setConversations] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [currentConversationId, setCurrentConversationId] = useState(null);
    useEffect(() => {

    const savedId = localStorage.getItem("conversationId");

    if (savedId) {
      setCurrentConversationId(savedId);
    }

  }, []);
  /**
   * Load all conversations for the default user
   * GET /conversations/user/{user_id}
   */
const loadConversations = useCallback(async () => {

  setIsLoading(true);
  setError(null);

  try {

    const data =
      await conversationService.listConversations();

    const list =
      Array.isArray(data) ? data : [];

    // Sort latest first
    const sorted =
      list.sort(
        (a,b)=>
          new Date(b.updated_at) -
          new Date(a.updated_at)
      );

    setConversations(sorted);

  } catch(err){

    setError(
      err.message ||
      "Failed to load conversations"
    );

    console.error(
      "Error loading conversations:",
      err
    );

  } finally {

    setIsLoading(false);

  }

}, []);

  /**
   * Create a new conversation
   * POST /conversations
   */
const createConversation = useCallback(async () => {

  // 🛑 If already in newest conversation AND it has no messages yet,
  // don't create another one
  if (currentConversationId && conversations.length > 0) {

    const newest = conversations[0];

    if (newest.conversation_id === currentConversationId) {
      return newest;
    }
  }

  setIsLoading(true);
  setError(null);

  try {

    const newConversation =
      await conversationService.createNewConversation();

    setConversations(prev => [
      newConversation,
      ...prev
    ]);

    setCurrentConversationId(
      newConversation.conversation_id
    );

    return newConversation;

  } catch (err) {

    setError(err.message || "Failed to create conversation");
    console.error("Error creating conversation:", err);
    throw err;

  } finally {

    setIsLoading(false);

  }

}, [currentConversationId, conversations]);
  /**
   * Select a conversation by ID (sidebar click)
   */
const selectConversation = useCallback((conversationId) => {

  setCurrentConversationId(conversationId);

  if (conversationId) {
    localStorage.setItem("conversationId", conversationId);
  }

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

if (currentConversationId === conversationId) {

  const remaining = conversations.filter(
    conv => conv.conversation_id !== conversationId
  );

  // ✅ If chats exist → open latest
  if (remaining.length > 0) {
    setCurrentConversationId(remaining[0].conversation_id);
  }
  // ✅ If no chats → go to welcome page
  else {
    setCurrentConversationId(null);
    localStorage.removeItem("conversationId");
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
   * Move conversation to top after message
   */
  const moveConversationToTop = useCallback((conversationId) => {

    setConversations(prev => {

      const selected =
        prev.find(
          c =>
          c.conversation_id ===
          conversationId
        );

      if(!selected) return prev;

      const updated = {
        ...selected,
        updated_at:
          new Date().toISOString()
      };

      const others =
        prev.filter(
          c =>
          c.conversation_id !==
          conversationId
        );

      return [
        updated,
        ...others
      ];

    });

  }, []);

  /**
   * Called by ChatPage when backend auto-creates a conversation
   * during /chat/stream (conversation_id was null)
   */
const handleAutoCreatedConversation = useCallback(
(newConversationId, backendTitle) => {

  if (!newConversationId) return;

  setCurrentConversationId(newConversationId);

  setConversations(prev => {

    let found = false;

    const updated = prev.map(c => {

      if (c.conversation_id === newConversationId) {

        found = true;

        return {
          ...c,
          title: backendTitle || c.title,
          updated_at: new Date().toISOString()
        };
      }

      return c;
    });

    // if conversation not found → add it
    if (!found) {
      return [
        {
          conversation_id: newConversationId,
          title: backendTitle || "New conversation",
          updated_at: new Date().toISOString()
        },
        ...updated
      ];
    }

    // IMPORTANT → return NEW array reference
    return [...updated];

  });

}, []);
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
  moveConversationToTop
};
};

export default useConversations;