import { useState, useCallback, useRef, useEffect } from "react";
import chatService from "../services/chatService";
import conversationService from "../services/conversationService";
import useDocumentUpload from "./useDocumentUpload";
import { MESSAGE_ROLES } from "../utils/constants";

const useChat = (
  conversationId,
  onConversationCreated,
  moveConversationToTop,
  userId
) => {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [streamingMessage, setStreamingMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  const activeConversationIdRef = useRef(conversationId);
  const abortRef = useRef(null);

  const addMessage = useCallback((msg) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

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

  // Load messages
  const loadMessages = useCallback(async () => {
    if (!conversationId) {
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

  // Ensure conversation exists
  const ensureConversation = useCallback(async () => {
    if (activeConversationIdRef.current) {
      return activeConversationIdRef.current;
    }

    try {
      const data = await conversationService.createNewConversation();
      const newId = data?.conversation_id;

      if (!newId) throw new Error("No conversation_id");

      activeConversationIdRef.current = newId;

      onConversationCreated?.(newId, null);
      moveConversationToTop?.(newId);

      return newId;
    } catch (err) {
      console.error("[useChat] ensureConversation error:", err);
      setError("Failed to start a session.");
      return null;
    }
  }, [onConversationCreated, moveConversationToTop]);

  // Send message
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

      // Upload file first
      if (file) {
        const convId = await ensureConversation();
        if (!convId) return;

        const uploadResult = await uploadDocument(file, convId);
        if (!uploadResult) return;

        if (!messageText.trim()) return;
      }

      // Add user message
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

          if (data.conversationId) {
            activeConversationIdRef.current = data.conversationId;

            const backendTitle =
              data.metadata?.conversation_title || null;

            onConversationCreated?.(data.conversationId, backendTitle);
            moveConversationToTop?.(data.conversationId);

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
      uploadDocument,
      onConversationCreated,
      moveConversationToTop,
      fetchSessionStatus,
    ]
  );

  // Stop streaming
  const stopStreaming = useCallback(() => {
    if (abortRef.current) {
      abortRef.current();
      abortRef.current = null;

      if (streamingMessage) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: MESSAGE_ROLES.ASSISTANT,
            content: streamingMessage,
            sources: [],
            timestamp: new Date().toISOString(),
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