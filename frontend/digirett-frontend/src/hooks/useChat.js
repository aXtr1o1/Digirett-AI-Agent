import { useState, useCallback, useRef } from "react";
import chatService from "../services/chatService";
import conversationService from "../services/conversationService";
import { MESSAGE_ROLES } from "../utils/constants";
import { useEffect } from "react";


const useChat = (conversationId, onConversationCreated) => {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [streamingMessage, setStreamingMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef(null);

  const loadMessages = useCallback(async () => {
    if (!conversationId) {
      console.log("[useChat] loadMessages skipped — no conversationId");
      return;
    }
    console.log("[useChat] loadMessages called for:", conversationId);
    setIsLoading(true);
    setError(null);

    try {
      const data = await conversationService.getConversationWithMessages(conversationId);
      
      console.log("=== BACKEND RAW MESSAGES ===");
      console.log(data.messages);
      console.log("===========================");
      console.log("[useChat] loadMessages got data:", data);

      const msgs = Array.isArray(data.messages) ? data.messages : [];
      console.log("[useChat] messages count:", msgs.length);

      const normalized = msgs.map((m) => ({
        id: m.message_id,          // ✅ ADD THIS
        role: m.role,
        content: m.content || "",
        sources: m.sources || [],
        timestamp: m.created_at || new Date().toISOString(),
      }));



      console.log("[useChat] normalized messages:", normalized);
      setMessages(normalized);
    } catch (err) {
      setError(err.message || "Failed to load messages");
      console.error("[useChat] loadMessages error:", err);
    } finally {
      setIsLoading(false);
    }
  }, [conversationId]);

  const sendMessage = useCallback(
    async (messageText) => {
      if (!messageText.trim()) return;

      const userMessage = {
        id: crypto.randomUUID(),  // ✅ ADD THIS
        role: MESSAGE_ROLES.USER,
        content: messageText,
        sources: [],
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsStreaming(true);
      setStreamingMessage("");
      setError(null);

      abortRef.current = chatService.sendMessage(
        conversationId,
        messageText,
        (token) => {
          setStreamingMessage((prev) => prev + token);
        },
        (data) => {
          const assistantMessage = {
            id: data.message_id || crypto.randomUUID(), // ✅ ADD THIS
            role: MESSAGE_ROLES.ASSISTANT,
            content: data.message,
            sources: data.sources || [],
            timestamp: new Date().toISOString(),
          };

          setMessages((prev) => [...prev, assistantMessage]);
          setStreamingMessage("");
          setIsStreaming(false);

          if (
            data.conversationId &&
            data.conversationId !== conversationId &&
            onConversationCreated
          ) {
            onConversationCreated(data.conversationId);
          }
        },
        (err) => {
          setError(err.message || "Failed to get response");
          setIsStreaming(false);
          setStreamingMessage("");
        }
      );
    },
    [conversationId, onConversationCreated]
  );

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
    if (conversationId) {
      loadMessages();
    }
  }, [conversationId, loadMessages]);


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