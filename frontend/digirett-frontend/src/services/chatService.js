// import { API_BASE_URL, DEFAULT_USER_ID } from "../utils/constants";

// const base = (API_BASE_URL || "auto.axtr.in").replace(/\/+$/, "");

// const WS_URL =
//   base.replace(/^https/, "wss").replace(/^http/, "ws") +
//   "/api/v1/chat/ws";

// console.log(WS_URL)

// // ─────────────────────────────────────────────────────────────────────────────

// const chatService = {
//   /**
//    * Send a message and stream the response.
//    *
//    * @param {string|null} conversationId  - existing conversation UUID, or null to auto-create
//    * @param {string}      message         - user query text
//    * @param {Function}    onChunk         - called with each streamed token string
//    * @param {Function}    onComplete      - called once with { message, sources, conversationId, messageId, metadata }
//    * @param {Function}    onError         - called with an Error object on failure
//    * @returns {Function}                  - cancel() function — same API as the old SSE version
//    */
//   sendMessage: (conversationId, message, onChunk, onComplete, onError) => {
//     let ws        = null;
//     let cancelled = false;

//     (async () => {
//       try {
//         const requestBody = {
//           query:       message,
//           user_id:     DEFAULT_USER_ID,
//           top_k:       3,
//           temperature: 0.7,
//         };

//         if (conversationId) {
//           requestBody.conversation_id = conversationId;
//         }

//         console.log("[chatService] Connecting to:", WS_URL);
//         console.log("[chatService] Payload:", requestBody);

//         ws = new WebSocket(WS_URL);
        
//         // Per-query state — same variables as the old SSE version
//         let fullMessage            = "";
//         let sources                = [];
//         let resolvedConversationId = conversationId;
//         let finalMetadata          = {};
//         let completeFired          = false;

//         // ── 1. Connection established → send the query ─────────────────
//         ws.onopen = () => {
//           if (cancelled) { ws.close(); return; }
//           console.log("[chatService] WS open — sending query");
//           ws.send(JSON.stringify(requestBody));
//         };

//         // ── 2. Receive streamed messages from backend ──────────────────
//         ws.onmessage = (e) => {
//           if (cancelled) return;

//           let event;
//           try {
//             event = JSON.parse(e.data);
//           } catch (err) {
//             console.warn("[chatService] WS parse error:", e.data, err);
//             return;
//           }

//           console.log("[chatService] event:", event.type, event);

//           switch (event.type) {

//             case "intent":
//               // Intent classified — informational only, no UI action needed
//               break;

//             case "sources":
//               sources = Array.isArray(event.data) ? event.data : [];
//               break;

//             case "token":
//               // ← This is the ChatGPT-like streaming: each token fires onChunk
//               const token = typeof event.data === "string" ? event.data : "";
//               fullMessage += token;
//               if (onChunk) onChunk(token);
//               break;

//             case "complete":
//               completeFired          = true;
//               finalMetadata          = event.metadata || {};
//               resolvedConversationId = finalMetadata.conversation_id || resolvedConversationId;

//               if (onComplete) {
//                 onComplete({
//                   message:        finalMetadata.full_answer || fullMessage,
//                   sources:        sources.map((url) =>
//                     typeof url === "string" ? { url, title: url } : url
//                   ),
//                   conversationId: resolvedConversationId,
//                   messageId:      finalMetadata.message_id || null,
//                   metadata:       finalMetadata,
//                 });
//               }

//               ws.close(1000, "query complete");
//               break;

//             case "error":
//               console.error("[chatService] backend error:", event.message);
//               if (onError) onError(new Error(event.message || "Stream error"));
//               ws.close();
//               break;

//             default:
//               console.log("[chatService] unknown event type:", event.type);
//           }
//         };

//         // ── 3. Connection closed ───────────────────────────────────────
//         ws.onclose = (e) => {
//           console.log("[chatService] WS closed | code:", e.code, "reason:", e.reason);
//           if (cancelled) return;
//           if (!completeFired && !fullMessage) {

//             if (onError) {
//               onError({
//                 message: "Connection lost. Please try again."
//               });
//             }

//             return;
//           }
//           // Closed before complete event arrived — fire onComplete with buffered text
//           if (!completeFired && fullMessage) {
//             if (onComplete) {
//               onComplete({
//                 message:        fullMessage,
//                 sources:        sources.map((url) =>
//                   typeof url === "string" ? { url, title: url } : url
//                 ),
//                 conversationId: resolvedConversationId,
//                 messageId:      null,
//                 metadata:       finalMetadata,
//               });
//             }
//           }
//         };

//         // ── 4. Network / protocol error ────────────────────────────────
//         ws.onerror = (e) => {

//         console.error("[chatService] WS error:", e);

//         if (!cancelled && onError) {

//           onError({
//             message: "Connection error. Please try again."
//           });

//         }

//         };

//       } catch (err) {
//         console.error("[chatService] setup error:", err);
//         if (!cancelled && onError) onError(err);
//       }
//     })();

//     // Return cancel function — same API as the old SSE abort()
//     return () => {
//       cancelled = true;
//       if (ws && ws.readyState === WebSocket.OPEN) {
//         ws.close(1000, "cancelled by user");
//         console.log("[chatService] WS cancelled by user");
//       }
//     };
//   },
// };

// export default chatService;

import { API_BASE_URL } from "../utils/constants";
import { DEFAULT_USER_ID } from "../utils/constants";
/* ────────────────────────────────────────────────────────────── */
/* Safe Base URL Handling                                        */
/* ────────────────────────────────────────────────────────────── */

const rawBase = API_BASE_URL || "http://localhost:8000";

const base = rawBase.startsWith("http")
  ? rawBase.replace(/\/+$/, "")
  : `http://${rawBase.replace(/\/+$/, "")}`;

const WS_URL =
  base.replace(/^https/, "wss").replace(/^http/, "ws") +
  "/api/v1/chat/ws";

console.log("WebSocket URL:", WS_URL);

/* ────────────────────────────────────────────────────────────── */

const chatService = {
  sendMessage: (conversationId, message, onChunk, onComplete, onError) => {
    let ws = null;
    let cancelled = false;

    (async () => {
      try {
        const requestBody = {
          query: message,
          user_id: DEFAULT_USER_ID, // ✅ use logged-in user
          top_k: 3,
          temperature: 0.7,
        };

        if (conversationId) {
          requestBody.conversation_id = conversationId;
        }

        console.log("[chatService] Connecting to:", WS_URL);
        console.log("[chatService] Payload:", requestBody);

        ws = new WebSocket(WS_URL);

        let fullMessage = "";
        let sources = [];
        let resolvedConversationId = conversationId;
        let finalMetadata = {};
        let completeFired = false;

        /* ─────────────── 1. On Open ─────────────── */
        ws.onopen = () => {
          if (cancelled) {
            ws.close();
            return;
          }

          console.log("[chatService] WS open — sending query");
          ws.send(JSON.stringify(requestBody));
        };

        /* ─────────────── 2. On Message ─────────────── */
        ws.onmessage = (e) => {
          if (cancelled) return;

          let event;
          try {
            event = JSON.parse(e.data);
          } catch (err) {
            console.warn("[chatService] WS parse error:", e.data);
            return;
          }

          console.log("[chatService] event:", event.type, event);

          switch (event.type) {
            case "intent":
              break;

            case "sources":
              sources = Array.isArray(event.data) ? event.data : [];
              break;

            case "token":
              const token =
                typeof event.data === "string" ? event.data : "";
              fullMessage += token;
              if (onChunk) onChunk(token);
              break;

            case "complete":
              completeFired = true;
              finalMetadata = event.metadata || {};

              resolvedConversationId =
                finalMetadata.conversation_id || resolvedConversationId;

              /* ✅ Save conversationId for history */
              if (resolvedConversationId) {
                localStorage.setItem(
                  "conversationId",
                  resolvedConversationId
                );
              }

              if (onComplete) {
                onComplete({
                  message:
                    finalMetadata.full_answer || fullMessage,
                  sources: sources.map((url) =>
                    typeof url === "string"
                      ? { url, title: url }
                      : url
                  ),
                  conversationId: resolvedConversationId,
                  messageId:
                    finalMetadata.message_id || null,
                  metadata: finalMetadata,
                });
              }

              ws.close(1000, "query complete");
              break;

            case "error":
              console.error(
                "[chatService] backend error:",
                event.message
              );
              if (onError)
                onError(
                  new Error(event.message || "Stream error")
                );
              ws.close();
              break;

            default:
              console.log(
                "[chatService] unknown event type:",
                event.type
              );
          }
        };

        /* ─────────────── 3. On Close ─────────────── */
        ws.onclose = (e) => {
          console.log(
            "[chatService] WS closed | code:",
            e.code,
            "reason:",
            e.reason
          );

          if (cancelled) return;

          if (!completeFired && !fullMessage) {
            if (onError) {
              onError({
                message:
                  "Connection lost. Please try again.",
              });
            }
            return;
          }

          if (!completeFired && fullMessage) {
            if (onComplete) {
              onComplete({
                message: fullMessage,
                sources: sources.map((url) =>
                  typeof url === "string"
                    ? { url, title: url }
                    : url
                ),
                conversationId: resolvedConversationId,
                messageId: null,
                metadata: finalMetadata,
              });
            }
          }
        };

        /* ─────────────── 4. On Error ─────────────── */
        ws.onerror = (e) => {
          console.error("[chatService] WS error:", e);

          if (!cancelled && onError) {
            onError({
              message:
                "Connection error. Please try again.",
            });
          }
        };
      } catch (err) {
        console.error("[chatService] setup error:", err);
        if (!cancelled && onError) onError(err);
      }
    })();

    /* ─────────────── Cancel Function ─────────────── */
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