import { useState, useCallback, useRef, useEffect } from "react";
import chatService from "../services/chatService";
import conversationService from "../services/conversationService";
import useDocumentUpload from "./useDocumentUpload";
import useDocumentUpload from "./useDocumentUpload";
import { MESSAGE_ROLES } from "../utils/constants";

const useChat = (
  conversationId,
  onConversationCreated,
  moveConversationToTop,
  userId
) => {
  const [messages, setMessages] = useState([]);
  const addMessage = useCallback((msg) => {
  setMessages((prev) => [...prev, msg]);
}, []);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [streamingMessage, setStreamingMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  const activeConversationIdRef = useRef(conversationId);
  const abortRef = useRef(null);

  const {
    uploadDocument,
    fetchSessionStatus,
    sessionStatus,
    uploadedDocs,
    isUploading,
    uploadError,
    clearUploadError,
    isUploadDisabled,
    isChatDisabled,
  } = useDocumentUpload(activeConversationIdRef.current, userId, addMessage);

  useEffect(() => {
    activeConversationIdRef.current = conversationId;
  }, [conversationId]);

  // ── Load messages for an existing conversation ────────────────────────────
  const loadMessages = useCallback(async () => {
    if (!conversationId) {
      setMessages([]);
      setMessages([]);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const data =
        await conversationService.getConversationWithMessages(conversationId);
      const msgs = Array.isArray(data.messages) ? data.messages : [];
      const normalized = msgs.map((m) => ({
        id: m.message_id,
        role: m.role,
        content: m.content || "",
        sources: m.sources || [],
        timestamp: m.created_at || new Date().toISOString(),
      }));
      setMessages(normalized);
    } catch (err) {
      console.error("[useChat] loadMessages error:", err);
      setError("Failed to load messages");
    } finally {
      setIsLoading(false);
    }
  }, [conversationId]);

  // ── Auto-create a conversation if none exists ─────────────────────────────
  // This lets users upload a doc on a brand-new chat without having to send
  // a text message first. The backend requires user_id = DEFAULT_USER_ID.
  const ensureConversation = useCallback(async () => {
    if (activeConversationIdRef.current) {
      return activeConversationIdRef.current;
    }

    try {
      // ✅ Correct method name: createNewConversation (not createConversation)
      // ✅ Returns response.data which has shape { conversation_id, ... }
      const data = await conversationService.createNewConversation();
      const newId = data?.conversation_id;

      if (!newId) {
        console.error("[useChat] createNewConversation returned no ID:", data);
        throw new Error("No conversation_id in response");
      }

      activeConversationIdRef.current = newId;

      if (onConversationCreated) onConversationCreated(newId, null);
      if (moveConversationToTop) moveConversationToTop(newId);

      return newId;
    } catch (err) {
      console.error("[useChat] ensureConversation error:", err);
      setError("Failed to start a session. Please try again.");
      return null;
    }
  }, [onConversationCreated, moveConversationToTop]);

  // ── Send message — accepts { text, file } OR a plain string ──────────────
  const sendMessage = useCallback(
    async (payload) => {
      const messageText =
        typeof payload === "string" ? payload : payload?.text ?? "";
      const file =
        typeof payload === "object" ? payload?.file ?? null : null;

      if (!messageText.trim() && !file) {
        setError("Please enter a message or attach a document.");
        return;
      }

      setError(null);

      // ── Step 1: Upload file if provided ───────────────────────────────────
      if (file) {
        // Auto-create conversation if needed — no blocking error shown to user
        const convId = await ensureConversation();
        if (!convId) return;

        const uploadResult = await uploadDocument(file, convId);
        if (!uploadResult) return;

        // Only a file was sent — done after upload, no text to stream
        if (!messageText.trim()) return;
      }

      // ── Step 2: Optimistically add user message ────────────────────────────
      const userMessage = {
        id: crypto.randomUUID(),
        role: MESSAGE_ROLES.USER,
        content: messageText,
        sources: [],
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsStreaming(true);
      setStreamingMessage("");

      let firstTokenReceived = false;
      const activeConversationId = activeConversationIdRef.current || null;
      let firstTokenReceived = false;
      const activeConversationId = activeConversationIdRef.current || null;

      // ── Step 3: Stream response via WebSocket ──────────────────────────────
      abortRef.current = chatService.sendMessage(
        activeConversationId,
        messageText,

        // STREAM TOKEN
        (token) => {
          if (!firstTokenReceived) {
            firstTokenReceived = true;
            setStreamingMessage("");
          }
          setStreamingMessage((prev) => prev + token);
        },
        // STREAM TOKEN
        (token) => {
          if (!firstTokenReceived) {
            firstTokenReceived = true;
            setStreamingMessage("");
          }
          setStreamingMessage((prev) => prev + token);
        },

        // COMPLETE
        (data) => {
          const assistantMessage = {
            id: data.messageId || crypto.randomUUID(),
            role: MESSAGE_ROLES.ASSISTANT,
            content: data.message,
            sources: data.sources || [],
            timestamp: new Date().toISOString(),
          };
        // COMPLETE
        (data) => {
          const assistantMessage = {
            id: data.messageId || crypto.randomUUID(),
            role: MESSAGE_ROLES.ASSISTANT,
            content: data.message,
            sources: data.sources || [],
            timestamp: new Date().toISOString(),
          };

          setMessages((prev) => [...prev, assistantMessage]);
          setStreamingMessage("");
          setIsStreaming(false);
          setMessages((prev) => [...prev, assistantMessage]);
          setStreamingMessage("");
          setIsStreaming(false);

          if (data.conversationId) {
            activeConversationIdRef.current = data.conversationId;
            const backendTitle = data.metadata?.conversation_title || null;
            if (onConversationCreated) onConversationCreated(data.conversationId, backendTitle);
            if (moveConversationToTop) moveConversationToTop(data.conversationId);
            fetchSessionStatus(data.conversationId);
          }
        },

        // ERROR
        (err) => {
          console.error("[useChat] stream error:", err);
          setError(err?.message || "Failed to generate response");
          setIsStreaming(false);
          setStreamingMessage("");
        }
      );
    },
    [
      ensureConversation,
      onConversationCreated,
      moveConversationToTop,
      uploadDocument,
      fetchSessionStatus,
    ]
  );

  // ── Stop streaming ────────────────────────────────────────────────────────
  // ── Stop streaming ────────────────────────────────────────────────────────
  const stopStreaming = useCallback(() => {
    if (abortRef.current) {
      abortRef.current();
      abortRef.current = null;
      if (streamingMessage) {
        setMessages((prev) => [
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: MESSAGE_ROLES.ASSISTANT,
            content: streamingMessage,
            sources: [],
            timestamp: new Date().toISOString(),
          },
          },
        ]);
      }
      setIsStreaming(false);
      setStreamingMessage("");
    }
  }, [streamingMessage]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setStreamingMessage("");
    setError(null);
  }, []);

  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

  useEffect(() => {
    if (conversationId) fetchSessionStatus(conversationId);
  }, [conversationId, fetchSessionStatus]);

  return {
    messages,
    isLoading,
    error,
    streamingMessage,
    isStreaming,
    sendMessage,
    loadMessages,
    stopStreaming,
    clearMessages,
    isUploading,
    uploadError,
    clearUploadError,
    uploadedDocs,
    sessionStatus,
    isUploadDisabled,
    isChatDisabled,
  };
};

export default useChat;