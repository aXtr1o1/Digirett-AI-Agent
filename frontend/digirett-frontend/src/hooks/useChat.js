import { useState, useCallback, useRef, useEffect } from "react";
import chatService from "../services/chatService";
import conversationService from "../services/conversationService";
import { MESSAGE_ROLES } from "../utils/constants";

const useChat = (
  conversationId,
  onConversationCreated,
  moveConversationToTop
) => {

  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [streamingMessage, setStreamingMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  const abortRef = useRef(null);

  // ✅ Load messages when selecting conversation
  const loadMessages = useCallback(async () => {

    if (!conversationId) {
      setMessages([]);   // important for welcome page
      return;
    }

    setIsLoading(true);
    setError(null);

    try {

      const data =
        await conversationService.getConversationWithMessages(conversationId);

      const msgs =
        Array.isArray(data.messages)
          ? data.messages
          : [];

      const normalized = msgs.map(m => ({
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

  // ✅ Send message (creates conversation if needed)
  const sendMessage = useCallback(async (messageText) => {

    if (!messageText.trim()) {
      setError("Please enter a message");
      return;
    }

    const userMessage = {
      id: crypto.randomUUID(),
      role: MESSAGE_ROLES.USER,
      content: messageText,
      sources: [],
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);

    setIsStreaming(true);
    setStreamingMessage("");
    setError(null);

    let firstTokenReceived = false;

    // If no conversation selected → backend will create one
    const activeConversationId = conversationId || null;

    abortRef.current = chatService.sendMessage(

      activeConversationId,
      messageText,

      // STREAM TOKEN
      (token) => {

        if (!firstTokenReceived) {
          firstTokenReceived = true;
          setStreamingMessage("");
        }

        setStreamingMessage(prev => prev + token);

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

        setMessages(prev => [...prev, assistantMessage]);
        setStreamingMessage("");
        setIsStreaming(false);

        // ✅ Backend created conversation
if (data.conversationId) {

  const backendTitle =
    data.metadata?.conversation_title;

  if (onConversationCreated) {
    onConversationCreated(
      data.conversationId,
      backendTitle
    );
  }

  if (moveConversationToTop) {
    moveConversationToTop(data.conversationId);
  }
}
      },

      // ERROR
      (err) => {

        console.error("Chat Error:", err);

        setError(
          err?.message ||
          "Failed to generate response"
        );

        setIsStreaming(false);
        setStreamingMessage("");
      }

    );

  }, [
    conversationId,
    onConversationCreated,
    moveConversationToTop
  ]);

  // ✅ Stop streaming
  const stopStreaming = useCallback(() => {

    if (abortRef.current) {

      abortRef.current();
      abortRef.current = null;

      if (streamingMessage) {

        setMessages(prev => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: MESSAGE_ROLES.ASSISTANT,
            content: streamingMessage,
            sources: [],
            timestamp: new Date().toISOString(),
          }
        ]);
      }

      setIsStreaming(false);
      setStreamingMessage("");
    }

  }, [streamingMessage]);

  // ✅ Clear messages (used for new chat welcome)
  const clearMessages = useCallback(() => {
    setMessages([]);
    setStreamingMessage("");
    setError(null);
  }, []);

  // ✅ Load when conversation changes
  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

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
  };
};

export default useChat;