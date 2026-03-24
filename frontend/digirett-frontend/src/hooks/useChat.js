import { useState, useCallback, useRef } from 'react';
import chatService from '../services/chatService';
import conversationService from '../services/conversationService';
import { MESSAGE_ROLES } from '../utils/constants';

/**
 * Custom hook for managing chat functionality
 */
const useChat = (conversationId) => {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [streamingMessage, setStreamingMessage] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef(null);

  /**
   * Load messages for a conversation
   */
  const loadMessages = useCallback(async () => {
    if (!conversationId) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await conversationService.getConversationMessages(conversationId);
      setMessages(response.messages || response || []);
    } catch (err) {
      setError(err.message || 'Failed to load messages');
      console.error('Error loading messages:', err);
    } finally {
      setIsLoading(false);
    }
  }, [conversationId]);

  /**
   * Send a message with streaming response
   */
  const sendMessage = useCallback(async (messageText) => {
    if (!conversationId || !messageText.trim()) return;

    // Add user message immediately
    const userMessage = {
      role: MESSAGE_ROLES.USER,
      content: messageText,
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setIsStreaming(true);
    setStreamingMessage('');
    setError(null);

    // Placeholder for assistant message
    const assistantMessageIndex = messages.length + 1;

    try {
      // Start streaming
      abortControllerRef.current = chatService.sendMessage(
        conversationId,
        messageText,
        // onChunk - called for each text chunk
        (chunk) => {
          setStreamingMessage(prev => prev + chunk);
        },
        // onComplete - called when streaming is done
        (data) => {
          const assistantMessage = {
            role: MESSAGE_ROLES.ASSISTANT,
            content: data.message,
            sources: data.sources || [],
            timestamp: new Date().toISOString(),
          };

          setMessages(prev => [...prev, assistantMessage]);
          setStreamingMessage('');
          setIsStreaming(false);
        },
        // onError
        (err) => {
          setError(err.message || 'Failed to get response');
          setIsStreaming(false);
          setStreamingMessage('');
        }
      );
    } catch (err) {
      setError(err.message || 'Failed to send message');
      setIsStreaming(false);
      setStreamingMessage('');
      console.error('Error sending message:', err);
    }
  }, [conversationId, messages.length]);

  /**
   * Stop the current streaming
   */
  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current();
      setIsStreaming(false);
      setStreamingMessage('');
    }
  }, []);

  /**
   * Clear all messages
   */
  const clearMessages = useCallback(() => {
    setMessages([]);
    setStreamingMessage('');
    setError(null);
  }, []);

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
