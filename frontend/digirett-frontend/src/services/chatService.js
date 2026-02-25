import { API_BASE_URL, DEFAULT_USER_ID } from "../utils/constants";

const base = (API_BASE_URL || "auto.axtr.in").replace(/\/+$/, "");

const WS_URL =
  base.replace(/^https/, "wss").replace(/^http/, "ws") +
  "/api/v1/chat/ws";

const chatService = {
  sendMessage: (conversationId, message, onChunk, onComplete, onError) => {
    let ws = null;
    let cancelled = false;

    (async () => {
      try {
        const body = {
          query: message,
          user_id: DEFAULT_USER_ID,
          top_k: 3,
          temperature: 0.7,
          ...(conversationId && { conversation_id: conversationId }),
        };

        ws = new WebSocket(WS_URL);

        let fullMessage = "";
        let sources = [];
        let resolvedConversationId = conversationId;
        let metadata = {};
        let completed = false;

        ws.onopen = () => {
          if (!cancelled) ws.send(JSON.stringify(body));
        };

        ws.onmessage = (e) => {
          if (cancelled) return;

          let event;
          try { event = JSON.parse(e.data); } catch { return; }

          switch (event.type) {

            case "sources":
              sources = event.data || [];
              break;

            case "token":
              fullMessage += event.data || "";
              onChunk?.(event.data || "");
              break;

            case "complete":
              completed = true;
              metadata = event.metadata || {};
              resolvedConversationId =
                metadata.conversation_id || resolvedConversationId;

              onComplete?.({
                message: metadata.full_answer || fullMessage,
                sources,
                conversationId: resolvedConversationId,
                messageId: metadata.message_id,
                metadata
              });

              ws.close();
              break;

            case "error":
              onError?.(new Error(event.message));
              ws.close();
              break;
          }
        };

        ws.onerror = () => {
          if (!cancelled) onError?.(new Error("Connection error"));
        };

        ws.onclose = () => {
          if (!completed && fullMessage) {
            onComplete?.({
              message: fullMessage,
              sources,
              conversationId: resolvedConversationId,
              messageId: null,
              metadata
            });
          }
        };

      } catch (err) {
        if (!cancelled) onError?.(err);
      }
    })();

    return () => {
      cancelled = true;
      if (ws?.readyState === WebSocket.OPEN) ws.close();
    };
  }
};

export default chatService;