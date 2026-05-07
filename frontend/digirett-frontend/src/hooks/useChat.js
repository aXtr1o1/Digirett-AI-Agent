import { useState, useCallback, useRef, useEffect } from "react";
import chatService from "../services/chatService";
import conversationService from "../services/conversationService";
import useDocumentUpload from "./useDocumentUpload";
import { MESSAGE_ROLES, API_BASE_URL } from "../utils/constants";

const useChat = (
  conversationId,
  onConversationCreated,
  moveConversationToTop,
  userId
) => {
  const [messages, setMessages] = useState([]);
  const addMessage = useCallback((msg) => {
    setMessages((prev) => [...prev, msg]);
  }, []);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [streamingMessage, setStreamingMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  // ✅ NEW: tracks whether we're processing/uploading a document (shows loading indicator)
  const [isProcessingDoc, setIsProcessingDoc] = useState(false);

  const activeConversationIdRef = useRef(conversationId);
  const abortRef = useRef(null);

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

  // ── Load messages for an existing conversation ────────────────────────────
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
        // ✅ Restore file messages correctly from DB
        type: m.type || "text",
        fileName: m.file_name || null,
        documentId: m.metadata?.document_id || null,
      }));
      setMessages(normalized);
    } catch (err) {
      console.error("[useChat] loadMessages error:", err);
      setError("Failed to load messages");
    } finally {
      setIsLoading(false);
    }
  }, [conversationId]);

  // ── Auto-create a conversation if none exists ─────────────────────────────
  const ensureConversation = useCallback(async () => {
    if (activeConversationIdRef.current) {
      return activeConversationIdRef.current;
    }
    try {
      const data = await conversationService.createNewConversation();
      const newId = data?.conversation_id;
      if (!newId) {
        throw new Error("No conversation_id in response");
      }
      activeConversationIdRef.current = newId;
      if (moveConversationToTop) moveConversationToTop(newId);
      return newId;
    } catch (err) {
      console.error("[useChat] ensureConversation error:", err);
      setError("Failed to start a session. Please try again.");
      return null;
    }
  }, [onConversationCreated, moveConversationToTop]);

  // ── Send message ──────────────────────────────────────────────────────────
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

      // ── File upload path ──────────────────────────────────────────────────
      if (file) {
        const convId = await ensureConversation();
        if (!convId) return;

        const hasQuery = !!messageText.trim();

        // ✅ STEP 1: Show the file bubble FIRST (GPT-style — user message on top)
        const fileMsgId = crypto.randomUUID();
        setMessages((prev) => [
          ...prev,
          {
            id: fileMsgId,
            role: MESSAGE_ROLES.USER,
            type: "file-with-text",
            fileName: file.name,
            documentId: null, // will be updated after upload
            content: messageText.trim() || null,
            sources: [],
            timestamp: new Date().toISOString(),
          },
        ]);

        // ✅ STEP 2: Show document processing indicator BELOW the file bubble
        setIsProcessingDoc(true);
        setIsStreaming(false);
        setStreamingMessage("");

        // ✅ STEP 3: Upload and get summary
        const uploadResult = await uploadDocument(file, convId, hasQuery);

        if (!uploadResult) {
          setIsProcessingDoc(false);
          return;
        }

        // ✅ STEP 4: Update the file bubble with the real document ID
        setMessages((prev) =>
          prev.map((m) =>
            m.id === fileMsgId
              ? { ...m, fileName: uploadResult.file_name || file.name, documentId: uploadResult.document_id }
              : m
          )
        );

        // ✅ STEP 5: If there's a summary (doc-only, no query), show it BELOW the file bubble
        if (!hasQuery && uploadResult.summary_text) {
          const summaryMsgId = crypto.randomUUID();
          setMessages((prev) => [
            ...prev,
            {
              id: summaryMsgId,
              role: MESSAGE_ROLES.ASSISTANT,
              type: "text",
              content: uploadResult.summary_text,
              sources: [],
              timestamp: new Date().toISOString(),
            },
          ]);
          setIsProcessingDoc(false);
        }

        // ── Save to DB (sequence matters for correct reload order) ────────
        // 1. Save file message FIRST
        try {
          await fetch(`${API_BASE_URL}/api/v1/documents/message/${convId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              role: "user",
              content: messageText.trim() || null,
              type: "file-with-text",
              file_name: uploadResult.file_name || file.name,
              document_id: uploadResult.document_id,
            }),
          });

          // For new conversations, trigger creation AFTER first message is in DB
          if (!conversationId && onConversationCreated) {
            onConversationCreated(convId, null);
          }
        } catch (err) {
          console.error("[useChat] ❌ save_file_message call failed:", err);
        }

        // 2. Save summary message SECOND (so it appears after file on reload)
        // Only save when there is NO query — with a query, doc_qa handles the response
        if (!hasQuery && uploadResult.summary_text) {
          try {
            await fetch(`${API_BASE_URL}/api/v1/documents/summary-message/${convId}`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                content: uploadResult.summary_text,
                document_id: uploadResult.document_id,
              }),
            });
          } catch (err) {
            console.error("[useChat] ❌ save_summary_message call failed:", err);
          }
        }

        // Doc only — no query to stream, stop here
        if (!hasQuery) {
          setIsProcessingDoc(false);
          return;
        }

        // ── File + query: stream the RAG response ─────────────────────────
        // Do NOT show summary here — doc_qa / legal / hybrid will stream the answer

        setIsProcessingDoc(false);
        setIsStreaming(true);
        setStreamingMessage("");

        let firstTokenReceived = false;
        const activeConversationId = activeConversationIdRef.current || null;

        abortRef.current = chatService.sendMessage(
          activeConversationId,
          messageText,
          (token) => {
            if (!firstTokenReceived) {
              firstTokenReceived = true;
              setStreamingMessage("");
            }
            setStreamingMessage((prev) => prev + token);
          },
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
              const backendTitle = data.metadata?.conversation_title || null;
              if (!conversationId && onConversationCreated) onConversationCreated(data.conversationId, backendTitle);
              if (moveConversationToTop) moveConversationToTop(data.conversationId);
              fetchSessionStatus(data.conversationId);
            }
          },
          (err) => {
            console.error("[useChat] stream error:", err);
            setError(err?.message || "Failed to generate response");
            setIsStreaming(false);
            setStreamingMessage("");
            setIsProcessingDoc(false);
          },
          { skipSaveUser: true }
        );

        return;
      }

      // ── Text only path ──────────────────────────────────────────────────
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: MESSAGE_ROLES.USER,
          content: messageText,
          sources: [],
          timestamp: new Date().toISOString(),
        },
      ]);

      setIsStreaming(true);
      setStreamingMessage("");

      let firstTokenReceived = false;
      const activeConversationId = activeConversationIdRef.current || null;

      abortRef.current = chatService.sendMessage(
        activeConversationId,
        messageText,
        (token) => {
          if (!firstTokenReceived) {
            firstTokenReceived = true;
            setStreamingMessage("");
          }
          setStreamingMessage((prev) => prev + token);
        },
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
            const backendTitle = data.metadata?.conversation_title || null;
            if (onConversationCreated) onConversationCreated(data.conversationId, backendTitle);
            if (moveConversationToTop) moveConversationToTop(data.conversationId);
            fetchSessionStatus(data.conversationId);
          }
        },
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
      onConversationCreated,
      moveConversationToTop,
      uploadDocument,
      fetchSessionStatus,
      conversationId,
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

  const clearMessages = useCallback(() => {
    setMessages([]);
    setStreamingMessage("");
    setError(null);
    setIsProcessingDoc(false);
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
    isProcessingDoc,        // ✅ NEW: expose for UI loading indicator
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