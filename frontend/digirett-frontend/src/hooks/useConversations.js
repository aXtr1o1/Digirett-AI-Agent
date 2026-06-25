import { useState, useCallback, useEffect } from "react";
import conversationService from "../services/conversationService";
import { supabase, getSupabaseClient } from "../lib/supabase";
import { useAuth } from "@clerk/clerk-react";

const isUuid = (str) => {
  if (!str) return false;
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(str);
};

const useConversations = () => {
  const { getToken, userId: clerkId } = useAuth();
  const [conversations, setConversations] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [currentConversationId, setCurrentConversationId] = useState(() => {
    const saved = localStorage.getItem("conversationId");
    return isUuid(saved) ? saved : null;
  });

  const [archivedIds, setArchivedIds] = useState(() => {
    try {
      const saved = localStorage.getItem("digirett_archived_conversation_ids");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const archiveConversation = useCallback((id) => {
    setArchivedIds((prev) => {
      const next = [...new Set([...prev, id])];
      localStorage.setItem("digirett_archived_conversation_ids", JSON.stringify(next));
      return next;
    });
  }, []);

  const restoreConversation = useCallback((id) => {
    setArchivedIds((prev) => {
      const next = prev.filter((item) => item !== id);
      localStorage.setItem("digirett_archived_conversation_ids", JSON.stringify(next));
      return next;
    });
  }, []);

  const loadConversations = useCallback(async () => {
    if (!clerkId) return;
    setIsLoading(true);
    setError(null);

    try {
      // 1. Get authenticated Supabase client
      const authClient = await getSupabaseClient(getToken);

      // 2. Resolve internal user_id
      console.log("[useConversations] Resolving user_id for:", clerkId);
      const { data: userData, error: userError } = await authClient
        .from("users")
        .select("user_id")
        .eq("clerk_user_id", clerkId)
        .maybeSingle();

      if (userError || !userData) {
        console.warn("[useConversations] Resolution failed:", userError || "No data");
        const data = await conversationService.listConversations();
        setConversations(Array.isArray(data) ? data : []);
        return;
      }

      const internalUserId = userData.user_id;

      // 3. Fetch conversations
      const { data, error: sbError } = await authClient
        .from("conversations")
        .select("conversation_id, user_id, title, is_deleted, created_at, updated_at")
        .eq("user_id", internalUserId)
        .or("is_deleted.eq.false,is_deleted.is.null")
        .order("updated_at", { ascending: false })
        .limit(50);

      if (sbError) throw sbError;

      const list = data || [];
      setConversations(list);

      // 4. Verify if the saved conversation belongs to this user
      const savedId = localStorage.getItem("conversationId");
      if (savedId) {
        const exists = list.some(c => c.conversation_id === savedId);
        if (!exists) {
          console.warn(`[useConversations] Invalid/Forbidden conversationId found (${savedId}). Clearing it.`);
          localStorage.removeItem("conversationId");
          setCurrentConversationId(null);
        }
      } else {
        // Always start fresh if no specific conversation is saved
        setCurrentConversationId(null);
      }
    } catch (err) {
      console.error("[useConversations] Supabase load failed:", err);
      // Final fallback to API
      try {
        const data = await conversationService.listConversations();
        setConversations(Array.isArray(data) ? data : []);
      } catch (innerErr) {
        setError(innerErr.message || "Failed to load conversations");
      }
    } finally {
      setIsLoading(false);
    }
  }, [clerkId, getToken]);

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
    if (conversationId && isUuid(conversationId)) {
      setCurrentConversationId(conversationId);
      localStorage.setItem("conversationId", conversationId);
    } else {
      setCurrentConversationId(null);
      localStorage.removeItem("conversationId");
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
        setCurrentConversationId(null);
        localStorage.removeItem("conversationId");
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
  const moveConversationToTop = useCallback((conversationId, backendTitle) => {

    setConversations(prev => {

      const selected =
        prev.find(
          c =>
            c.conversation_id ===
            conversationId
        );

      if (!selected) return prev;

      const updated = {
        ...selected,
        updated_at:
          new Date().toISOString()
      };

      if (backendTitle) {
        updated.title = backendTitle;
      }

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
      localStorage.setItem("conversationId", newConversationId);

      setConversations(prev => {

        let found = false;

        const updated = prev.map(c => {

          if (c.conversation_id === newConversationId) {

            found = true;

            return {
              ...c,

              // ✅ Always update title if backend sends it
              title:
                backendTitle
                  ? backendTitle
                  : c.title || "New Chat",

              updated_at:
                new Date().toISOString()
            };
          }

          return c;
        });

        // If not found → create
        if (!found) {

          return [
            {
              conversation_id: newConversationId,

              title:
                backendTitle || "New Chat",

              updated_at:
                new Date().toISOString()
            },

            ...updated
          ];
        }

        return [...updated];

      });

    }, []);

  const updateEscalationStatus = useCallback((conversationId, isEscalated) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.conversation_id === conversationId ? { ...c, is_escalated: isEscalated } : c
      )
    );
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
    moveConversationToTop,
    updateEscalationStatus,
    archivedIds,
    archiveConversation,
    restoreConversation
  };
};

export default useConversations;