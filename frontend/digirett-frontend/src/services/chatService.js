import { API_BASE_URL, API_ENDPOINTS } from '../utils/constants';

/**
 * Chat Service
 * Handles streaming chat messages using Server-Sent Events (SSE)
 */
const chatService = {
  /**
   * Send a message and receive streaming response
   * POST /chat/message (with SSE)
   * 
   * @param {string} conversationId - The conversation ID
   * @param {string} message - The user's message
   * @param {function} onChunk - Callback for each chunk of text
   * @param {function} onComplete - Callback when streaming is complete
   * @param {function} onError - Callback for errors
   * @returns {function} Abort function to cancel the stream
   */
  sendMessage: async (conversationId, message, onChunk, onComplete, onError) => {
    const controller = new AbortController();
    const signal = controller.signal;

    try {
      // Get Clerk token
      const clerkToken = await window.Clerk?.session?.getToken();
      
      if (!clerkToken) {
        throw new Error('No authentication token available');
      }

      // Make the fetch request for SSE
      const response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.CHAT.MESSAGE}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${clerkToken}`,
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: message,
        }),
        signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Read the stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullMessage = '';
      let sources = [];

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          break;
        }

        // Decode the chunk
        buffer += decoder.decode(value, { stream: true });
        
        // Process complete SSE messages
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6); // Remove 'data: ' prefix
            
            if (data === '[DONE]') {
              // Stream complete
              if (onComplete) {
                onComplete({
                  message: fullMessage,
                  sources: sources,
                });
              }
              return;
            }

            try {
              const parsed = JSON.parse(data);
              
              // Handle text chunks
              if (parsed.content) {
                fullMessage += parsed.content;
                if (onChunk) {
                  onChunk(parsed.content);
                }
              }
              
              // Handle sources
              if (parsed.sources) {
                sources = parsed.sources;
              }
              
              // Handle complete message with sources
              if (parsed.message && parsed.sources) {
                fullMessage = parsed.message;
                sources = parsed.sources;
              }
            } catch (e) {
              console.error('Error parsing SSE data:', e);
            }
          }
        }
      }

      // If we reach here without [DONE], call onComplete anyway
      if (onComplete) {
        onComplete({
          message: fullMessage,
          sources: sources,
        });
      }

    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Stream aborted');
      } else {
        console.error('Error in chat stream:', error);
        if (onError) {
          onError(error);
        }
      }
    }

    // Return abort function
    return () => controller.abort();
  },

  /**
   * Send a message without streaming (fallback)
   * POST /chat/message (regular request)
   */
  sendMessageNoStream: async (conversationId, message) => {
    try {
      const clerkToken = await window.Clerk?.session?.getToken();
      
      if (!clerkToken) {
        throw new Error('No authentication token available');
      }

      const response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.CHAT.MESSAGE}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${clerkToken}`,
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: message,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error sending message:', error);
      throw error;
    }
  },
};

export default chatService;
