import React from "react";
import { useUser } from "@clerk/clerk-react";
import MessageList from "./MessageList";
import MessageComposer from "./MessageComposer";
import ErrorMessage from "../common/ErrorMessage";
import useChat from "../../hooks/useChat";
import EscalationStatusCard from "./EscalationStatusCard";

const ChatContainer = ({
  conversationId,
  conversations = [],
  onConversationCreated,
  moveConversationToTop,
  userId,
  theme = "dark",
  onEscalated, // New prop
}) => {
  const isDark = theme === "dark";
  const { user } = useUser();
  const role = user?.publicMetadata?.role || "user";
  const isLawyerView = role === "lawyer" || role === "admin";

  const currentConversation = conversations.find(c => c.conversation_id === conversationId);
  const conversationTitle = currentConversation?.title || "New Chat";

  const {
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
    clearError,
    isUploading,
    uploadError,
    clearUploadError,
    uploadedDocs,
    sessionStatus,
    isUploadDisabled,
    isChatDisabled,
    isEscalated,
    escalate,
  } = useChat(
    conversationId,
    onConversationCreated,
    moveConversationToTop,
    userId,
  );

  // Notify parent of escalation status
  const onEscalatedRef = React.useRef(onEscalated);
  React.useEffect(() => {
    onEscalatedRef.current = onEscalated;
  }, [onEscalated]);

  React.useEffect(() => {
    if (onEscalatedRef.current) {
      onEscalatedRef.current(isEscalated);
    }
  }, [isEscalated]);

  // ✅ PREVENT INPUT CLEARING DURING AUTO-CREATE TRANSITION
  const prevConvIdRef = React.useRef(conversationId);
  const [composerKey, setComposerKey] = React.useState(conversationId || "new-chat");

  React.useEffect(() => {
    const prev = prevConvIdRef.current;
    prevConvIdRef.current = conversationId;

    if (prev === null && conversationId !== null) {
      // Transitioning from New Chat to Auto-Created Chat.
      // Do NOT change the key, so the composer does NOT remount and wipe typed text.
      return;
    } else if (prev !== conversationId) {
      // Switched to a different chat from the sidebar. Change key to clear input.
      setComposerKey(conversationId || "new-chat");
    }
  }, [conversationId]);

  React.useEffect(() => {
    const handleNewChatTriggered = () => {
      setComposerKey("new-chat-" + Date.now());
    };
    window.addEventListener("new_chat_triggered", handleNewChatTriggered);
    return () => window.removeEventListener("new_chat_triggered", handleNewChatTriggered);
  }, []);

  return (
    <div className="flex flex-col h-full w-full bg-transparent">
      {(error || uploadError) && (
        <div className="px-6 pt-4">
          <ErrorMessage
            message={error || uploadError}
            onRetry={error ? clearError : clearUploadError}
          />
        </div>
      )}

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
            conversationId={conversationId}
            conversationTitle={conversationTitle}
          />

          {/* ✅ Status Card removed from here — moved to Right Sidebar */}
        </div>
      </div>

      <div className="flex-shrink-0 bg-transparent">
        <div id="chat-composer-container" className="max-w-2xl mx-auto w-full px-4 py-4">
          <MessageComposer
            key={composerKey}
            onSend={sendMessage}
            disabled={isLoading || isChatDisabled}
            isStreaming={isStreaming}
            isProcessingDoc={isProcessingDoc}
            onStop={stopStreaming}
            theme={theme}
            isUploading={isUploading}
            uploadedDocs={uploadedDocs}
            sessionStatus={sessionStatus}
            isUploadDisabled={isUploadDisabled}
            uploadError={uploadError}
            onClearUploadError={clearUploadError}
            onEscalate={escalate}
            isEscalated={isEscalated}
            showEscalate={role === "user" || !role}
            messageCount={messages.length}
          />
        </div>
        <p className={`text-center text-xs pb-3 ${isDark ? "text-gray-500" : "text-gray-400"}`}>
          DigiRett can make mistakes. Verify important legal information.
        </p>
      </div>
    </div>
  );
};

export default ChatContainer;