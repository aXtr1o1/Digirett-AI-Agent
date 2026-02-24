import { API_BASE_URL, DEFAULT_USER_ID } from "../utils/constants";
import { API_BASE_URL, DEFAULT_USER_ID } from "../utils/constants";

/**
 * Chat Service — WebSocket streaming
 *
 * Connects to ws://host/api/v1/chat/ws
 * Streams tokens back exactly like ChatGPT (character by character via onChunk)
 * Chat Service — WebSocket streaming
 *
 * Connects to ws://host/api/v1/chat/ws
 * Streams tokens back exactly like ChatGPT (character by character via onChunk)
 *
 * Backend message format:
 *   { type: "intent",   data: { intent: "LEGAL", language: "norwegian" } }
 *   { type: "sources",  data: ["url1", "url2"] }
 *   { type: "token",    data: "partial text" }          ← streamed word by word
 *   { type: "complete", metadata: { conversation_id, message_id, ... } }
 *   { type: "error",    message: "..." }
 * Backend message format:
 *   { type: "intent",   data: { intent: "LEGAL", language: "norwegian" } }
 *   { type: "sources",  data: ["url1", "url2"] }
 *   { type: "token",    data: "partial text" }          ← streamed word by word
 *   { type: "complete", metadata: { conversation_id, message_id, ... } }
 *   { type: "error",    message: "..." }
 */

// ── Derive WebSocket URL from API_BASE_URL ────────────────────────────────
// Strips any trailing /api/v1 or trailing slash so we can append the full path cleanly.
// Example:
//   API_BASE_URL = "http://localhost:8000"       → ws://localhost:8000/api/v1/chat/ws
//   API_BASE_URL = "http://localhost:8000/api/v1" → ws://localhost:8000/api/v1/chat/ws
const SAFE_API_BASE_URL =
  typeof API_BASE_URL === "string" && API_BASE_URL.length > 0
    ? API_BASE_URL
    : "http://localhost:8000";

const cleanBase = API_BASE_URL.replace(/\/+$/, "");

const WS_URL =
  cleanBase
    .replace(/^https/, "wss")
    .replace(/^http/, "ws") +
  "/api/v1/chat/ws";

// ─────────────────────────────────────────────────────────────────────────────

const chatService = {
  /**
   * Send a message and stream the response.
   *
   * @param {string|null} conversationId  - existing conversation UUID, or null to auto-create
   * @param {string}      message         - user query text
   * @param {Function}    onChunk         - called with each streamed token string
   * @param {Function}    onComplete      - called once with { message, sources, conversationId, messageId, metadata }
   * @param {Function}    onError         - called with an Error object on failure
   * @returns {Function}                  - cancel() function — same API as the old SSE version
   */
  /**
   * Send a message and stream the response.
   *
   * @param {string|null} conversationId  - existing conversation UUID, or null to auto-create
   * @param {string}      message         - user query text
   * @param {Function}    onChunk         - called with each streamed token string
   * @param {Function}    onComplete      - called once with { message, sources, conversationId, messageId, metadata }
   * @param {Function}    onError         - called with an Error object on failure
   * @returns {Function}                  - cancel() function — same API as the old SSE version
   */
  sendMessage: (conversationId, message, onChunk, onComplete, onError) => {
    let ws        = null;
    let cancelled = false;
    let ws        = null;
    let cancelled = false;

    (async () => {
      try {
        const requestBody = {
          query:       message,
          user_id:     DEFAULT_USER_ID,
          top_k:       3,
          query:       message,
          user_id:     DEFAULT_USER_ID,
          top_k:       3,
          temperature: 0.7,
        };

        if (conversationId) {
          requestBody.conversation_id = conversationId;
        }

        console.log("[chatService] Connecting to:", WS_URL);
        console.log("[chatService] Payload:", requestBody);

        ws = new WebSocket(WS_URL);
        
        // Per-query state — same variables as the old SSE version
        let fullMessage            = "";
        let sources                = [];
        let resolvedConversationId = conversationId;
        let finalMetadata          = {};
        let completeFired          = false;

        // ── 1. Connection established → send the query ─────────────────
        ws.onopen = () => {
          if (cancelled) { ws.close(); return; }
          console.log("[chatService] WS open — sending query");
          ws.send(JSON.stringify(requestBody));
        };

        // ── 2. Receive streamed messages from backend ──────────────────
        ws.onmessage = (e) => {
          if (cancelled) return;

          let event;
          try {
            event = JSON.parse(e.data);
          } catch (err) {
            console.warn("[chatService] WS parse error:", e.data, err);
            return;
          }

          console.log("[chatService] event:", event.type, event);
        let finalMetadata          = {};
        let completeFired          = false;

        // ── 1. Connection established → send the query ─────────────────
        ws.onopen = () => {
          if (cancelled) { ws.close(); return; }
          console.log("[chatService] WS open — sending query");
          ws.send(JSON.stringify(requestBody));
        };

        // ── 2. Receive streamed messages from backend ──────────────────
        ws.onmessage = (e) => {
          if (cancelled) return;

          let event;
          try {
            event = JSON.parse(e.data);
          } catch (err) {
            console.warn("[chatService] WS parse error:", e.data, err);
            return;
          }

          console.log("[chatService] event:", event.type, event);

          switch (event.type) {

            case "intent":
              // Intent classified — informational only, no UI action needed
              break;

            case "sources":
              sources = Array.isArray(event.data) ? event.data : [];
              break;

            case "token":
              // ← This is the ChatGPT-like streaming: each token fires onChunk
              const token = typeof event.data === "string" ? event.data : "";
              fullMessage += token;
              if (onChunk) onChunk(token);
              break;

            case "complete":
              completeFired          = true;
              finalMetadata          = event.metadata || {};
              resolvedConversationId = finalMetadata.conversation_id || resolvedConversationId;
          switch (event.type) {

            case "intent":
              // Intent classified — informational only, no UI action needed
              break;

            case "sources":
              sources = Array.isArray(event.data) ? event.data : [];
              break;

            case "token":
              // ← This is the ChatGPT-like streaming: each token fires onChunk
              const token = typeof event.data === "string" ? event.data : "";
              fullMessage += token;
              if (onChunk) onChunk(token);
              break;

            case "complete":
              completeFired          = true;
              finalMetadata          = event.metadata || {};
              resolvedConversationId = finalMetadata.conversation_id || resolvedConversationId;

              if (onComplete) {
                onComplete({
                  message:        finalMetadata.full_answer || fullMessage,
                  sources:        sources.map((url) =>
                    typeof url === "string" ? { url, title: url } : url
                  ),
                  conversationId: resolvedConversationId,
                  messageId:      finalMetadata.message_id || null,
                  metadata:       finalMetadata,
                });
              }

              ws.close(1000, "query complete");
              break;

            case "error":
              console.error("[chatService] backend error:", event.message);
              if (onError) onError(new Error(event.message || "Stream error"));
              ws.close();
              break;

            default:
              console.log("[chatService] unknown event type:", event.type);
          }
        };

        // ── 3. Connection closed ───────────────────────────────────────
        ws.onclose = (e) => {
          console.log("[chatService] WS closed | code:", e.code, "reason:", e.reason);
          if (cancelled) return;
          if (!completeFired && !fullMessage) {

            if (onError) {
              onError({
                message: "Connection lost. Please try again."
              });
            }

            return;
          }
          // Closed before complete event arrived — fire onComplete with buffered text
          if (!completeFired && fullMessage) {
            if (onComplete) {
              onComplete({
                message:        fullMessage,
                sources:        sources.map((url) =>
                  typeof url === "string" ? { url, title: url } : url
                ),
                conversationId: resolvedConversationId,
                messageId:      null,
                metadata:       finalMetadata,
              });
            }
          }
        };

        // ── 4. Network / protocol error ────────────────────────────────
        ws.onerror = (e) => {

        console.error("[chatService] WS error:", e);

        if (!cancelled && onError) {

          onError({
            message: "Connection error. Please try again."
          });

        }

        };

      } catch (err) {
        console.error("[chatService] setup error:", err);
        if (!cancelled && onError) onError(err);
        console.error("[chatService] setup error:", err);
        if (!cancelled && onError) onError(err);
      }
    })();

    // Return cancel function — same API as the old SSE abort()
    return () => {
      cancelled = true;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1000, "cancelled by user");
        console.log("[chatService] WS cancelled by user");
      }
    };
    // Return cancel function — same API as the old SSE abort()
    return () => {
      cancelled = true;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1000, "cancelled by user");
        console.log("[chatService] WS cancelled by user");
      }
    };
  },
};

export default chatService;