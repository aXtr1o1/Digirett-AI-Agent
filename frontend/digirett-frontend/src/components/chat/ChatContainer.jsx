import React from "react";
import MessageList from "./MessageList";
import MessageComposer from "./MessageComposer";
import ErrorMessage from "../common/ErrorMessage";
import useChat from "../../hooks/useChat";

const ChatContainer = ({
  conversationId,
  onConversationCreated,
  moveConversationToTop,
  userId,
  theme = "dark",
}) => {
  const isDark = theme === "dark";

  const {
    // ── chat state ──────────────────────────────────────────────────────────
    messages,
    isLoading,
    error,
    streamingMessage,
    isStreaming,
    isProcessingDoc,
    sendMessage,
    loadMessages,
    stopStreaming,
    clearMessages,
    // ── document upload state ───────────────────────────────────────────────
    isUploading,
    uploadError,
    clearUploadError,
    uploadedDocs,
    sessionStatus,
    isUploadDisabled,
    isChatDisabled,
  } = useChat(
    conversationId,
    onConversationCreated,
    moveConversationToTop,
    userId,
  );

  return (
    <div className="flex flex-col h-full w-full bg-transparent">

      {/* ── Error banner ───────────────────────────────────────────────────── */}
      {(error || uploadError) && (
        <div className="px-6 pt-4">
          <ErrorMessage
            message={error || uploadError}
            onRetry={error ? loadMessages : clearUploadError}
          />
        </div>
      )}

      {/* ── Scrollable message area ─────────────────────────────────────────── */}
      <div
        className="flex-1 overflow-y-auto overflow-x-hidden"
        style={{ overscrollBehavior: "none" }}
      >
        <div className="max-w-2xl mx-auto w-full px-4 pt-6 pb-4">
          <MessageList
            messages={messages}
            isLoading={isLoading}
            streamingMessage={streamingMessage}
            isStreaming={isStreaming}
            isProcessingDoc={isProcessingDoc}
            theme={theme}
          />
        </div>
      </div>

      {/* ── Input bar ──────────────────────────────────────────────────────── */}
      <div className="flex-shrink-0 bg-transparent">
        <div className="max-w-2xl mx-auto w-full px-4 py-4">
          <MessageComposer
            onSend={sendMessage}
            disabled={isLoading || isChatDisabled}
            isStreaming={isStreaming}
            isProcessingDoc={isProcessingDoc}
            onStop={stopStreaming}
            theme={theme}
            // ── document upload props ────────────────────────────────────────
            isUploading={isUploading}
            uploadedDocs={uploadedDocs}
            sessionStatus={sessionStatus}
            isUploadDisabled={isUploadDisabled}
            uploadError={uploadError}
            onClearUploadError={clearUploadError}
          />
        </div>
        <p
          className={`text-center text-xs pb-3 ${isDark ? "text-gray-500" : "text-gray-400"
            }`}
        >
          DigiRett can make mistakes. Verify important legal information.
        </p>
      </div>

    </div>
  );
};

export default ChatContainer;