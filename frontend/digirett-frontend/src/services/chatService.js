import { API_BASE_URL, API_ENDPOINTS, DEFAULT_USER_ID } from "../utils/constants";

/**
 * Chat Service — SSE streaming via POST /chat/stream
 *
 * Backend event format:
 *   data: {"type": "intent",   "data": {"intent": "LEGAL", "language": "norwegian"}}
 *   data: {"type": "sources",  "data": ["url1", "url2"]}
 *   data: {"type": "token",    "data": "partial text"}
 *   data: {"type": "complete", "metadata": {conversation_id, message_id, full_answer, ...}}
 *   data: {"type": "error",    "message": "..."}
 */
const chatService = {
  sendMessage: (conversationId, message, onChunk, onComplete, onError) => {
    const controller = new AbortController();

    (async () => {
      try {
        const requestBody = {
          query: message,
          user_id: DEFAULT_USER_ID,
          top_k: 3,
          temperature: 0.7,
        };

        if (conversationId) {
          requestBody.conversation_id = conversationId;
        }

        console.log("[chatService] POST /chat/stream body:", requestBody);

        // TODO: uncomment when backend auth is ready
        // const clerkToken = await window.Clerk?.session?.getToken();

        const response = await fetch(
          `${API_BASE_URL}${API_ENDPOINTS.CHAT.STREAM}`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Accept: "text/event-stream",
              // "Authorization": `Bearer ${clerkToken}`,
            },
            body: JSON.stringify(requestBody),
            signal: controller.signal,
          }
        );

        if (!response.ok) {
          const errorText = await response.text();
          console.error("[chatService] HTTP error:", response.status, errorText);
          throw new Error(`Server error: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let fullMessage = "";
        let sources = [];
        let resolvedConversationId = conversationId;
        let finalMetadata = {};
        let completeFired = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            console.log("[chatService] stream done");
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          console.log("[chatService] raw buffer chunk:", buffer.slice(-200));

          // Split on double newline (standard SSE separator)
          const events = buffer.split("\n\n");
          buffer = events.pop() || "";

          for (const eventBlock of events) {
            // Each block may have multiple lines; find the data line
            const lines = eventBlock.split("\n");
            for (const line of lines) {
              if (!line.startsWith("data:")) continue;

              const jsonStr = line.replace(/^data:\s*/, "");
              if (!jsonStr || jsonStr === "[DONE]") continue;

              try {
                const event = JSON.parse(jsonStr);
                console.log("[chatService] event:", event.type, event);

                if (event.type === "intent") {
                  // Informational only
                }
                else if (event.type === "sources") {
                  sources = Array.isArray(event.data) ? event.data : [];
                }
                else if (event.type === "token") {
                  const token = typeof event.data === "string" ? event.data : "";
                  fullMessage += token;
                  if (onChunk) onChunk(token);
                }
                else if (event.type === "complete") {
                  completeFired = true;
                  finalMetadata = event.metadata || {};
                  resolvedConversationId = finalMetadata.conversation_id || resolvedConversationId;
                  const finalAnswer = finalMetadata.full_answer || fullMessage;

                  if (onComplete) {
                    onComplete({
                      message: finalAnswer,
                      sources: sources.map((url) =>
                        typeof url === "string" ? { url, title: url } : url
                      ),
                      conversationId: resolvedConversationId,
                      messageId: finalMetadata.message_id || null,
                      metadata: finalMetadata,
                    });
                  }
                }
                else if (event.type === "error") {
                  if (onError) onError(new Error(event.message || "Stream error"));
                }
              } catch (parseErr) {
                console.warn("[chatService] parse error for line:", jsonStr, parseErr);
              }
            }
          }
        }

        // Stream ended without complete event
        if (!completeFired && fullMessage) {
          console.log("[chatService] stream ended without complete event, firing onComplete");
          if (onComplete) {
            onComplete({
              message: fullMessage,
              sources: sources.map((url) =>
                typeof url === "string" ? { url, title: url } : url
              ),
              conversationId: resolvedConversationId,
              messageId: null,
              metadata: finalMetadata,
            });
          }
        }

      } catch (err) {
        if (err.name === "AbortError") {
          console.log("[chatService] stream aborted");
        } else {
          console.error("[chatService] stream error:", err);
          if (onError) onError(err);
        }
      }
    })();

    return () => controller.abort();
  },
};

export default chatService;