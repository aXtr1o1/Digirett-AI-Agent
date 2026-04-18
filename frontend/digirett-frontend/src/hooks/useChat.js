import { useState, useCallback, useRef, useEffect } from "react";
import chatService from "../services/chatService";
import conversationService from "../services/conversationService";
import useDocumentUpload from "./useDocumentUpload";
import { MESSAGE_ROLES } from "../utils/constants";

const useChat = (
  conversationId,
  onConversationCreated,
  moveConversationToTop,
  userId           // ← pass user.id from your auth context here
) => {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [streamingMessage, setStreamingMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  // Track the conversation ID that may have just been created by the backend
  const activeConversationIdRef = useRef(conversationId);

  const abortRef = useRef(null);

  // ── Document upload hook ──────────────────────────────────────────────────
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
  } = useDocumentUpload(conversationId, userId);

  // Keep ref in sync with prop
  useEffect(() => {
    activeConversationIdRef.current = conversationId;
  }, [conversationId]);

  // ── Load messages when selecting conversation ─────────────────────────────
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

  // ── Send message — accepts { text, file } OR a plain string ──────────────
  const sendMessage = useCallback(
    async (payload) => {
      // Support both old string calls and new { text, file } calls
      const messageText =
        typeof payload === "string" ? payload : payload?.text ?? "";
      const file =
        typeof payload === "object" ? payload?.file ?? null : null;

      if (!messageText.trim() && !file) {
        setError("Please enter a message or attach a document.");
        return;
      }

      // ── Step 1: Upload file FIRST if provided ──────────────────────────
      // At this point conversationId may be null (new chat).
      // We need an ID to upload. If there's no conversationId yet,
      // we skip the upload here and let the user know they need to
      // send a first message to create the conversation before uploading.
      if (file) {
        const convId = activeConversationIdRef.current;
        if (!convId) {
          setError(
            "Please send a text message first to start a session, then attach a document."
          );
          return;
        }
        const uploadResult = await uploadDocument(file, convId);
        if (!uploadResult) {
          // uploadDocument already set uploadError; stop here
          return;
        }
        // If user only attached a file with no text, we're done after upload
        if (!messageText.trim()) return;
      }

      // ── Step 2: Optimistically add user message ────────────────────────
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
      setError(null);

      let firstTokenReceived = false;
      const activeConversationId = activeConversationIdRef.current || null;

      // ── Step 3: Stream response ────────────────────────────────────────
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
            // Update ref so future uploads use the new ID
            activeConversationIdRef.current = data.conversationId;

            const backendTitle = data.metadata?.conversation_title || null;

            if (onConversationCreated) {
              onConversationCreated(data.conversationId, backendTitle);
            }
            if (moveConversationToTop) {
              moveConversationToTop(data.conversationId);
            }

            // Refresh session status now that we have a real conversationId
            fetchSessionStatus(data.conversationId);

            console.log("WS COMPLETE:", data);
          }
        },

        // ERROR
        (err) => {
          console.error("Chat Error:", err);
          setError(err?.message || "Failed to generate response");
          setIsStreaming(false);
          setStreamingMessage("");
        }
      );
    },
    [
      conversationId,
      onConversationCreated,
      moveConversationToTop,
      uploadDocument,
      fetchSessionStatus,
    ]
  );

  // ── Stop streaming ────────────────────────────────────────────────────────
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

  // ── Clear messages (new chat) ─────────────────────────────────────────────
  const clearMessages = useCallback(() => {
    setMessages([]);
    setStreamingMessage("");
    setError(null);
  }, []);

  // ── Load on conversation change ───────────────────────────────────────────
  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

  // ── Fetch session status when conversationId becomes available ────────────
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
    // ── document upload state (pass these to MessageComposer) ──
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