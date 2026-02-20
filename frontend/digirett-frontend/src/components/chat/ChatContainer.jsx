import React, { useEffect, useRef } from "react";
import MessageList from "./MessageList";
import MessageComposer from "./MessageComposer";
import ErrorMessage from "../common/ErrorMessage";
import useChat from "../../hooks/useChat";

const ChatContainer = ({ conversationId, onConversationCreated, theme = "dark" }) => {
  const prevIdRef = useRef(undefined);
  const isDark = theme === "dark";

  const {
    messages,
    isLoading,
    error,
    streamingMessage,
    isStreaming,
    sendMessage,
    loadMessages,
    stopStreaming,
  } = useChat(conversationId, onConversationCreated);

  return (
    <div className={`flex flex-col h-full ${isDark ? "bg-black" : "bg-gray-50"}`}>
      {error && (
        <div className="p-4">
          <ErrorMessage message={error} onRetry={loadMessages} />
        </div>
      )}

      <div className="flex-1 flex justify-center overflow-hidden">
        <div className="w-full max-w-4xl flex flex-col h-full">

          {/* ✅ SCROLLABLE MESSAGE AREA */}
          <div className="flex-1 overflow-y-auto px-4">
            <MessageList
              messages={messages}
              isLoading={isLoading}
              streamingMessage={streamingMessage}
              isStreaming={isStreaming}
              theme={theme}
            />
          </div>

          {/* ✅ FIXED INPUT AT BOTTOM */}
          <div className={`border-t p-4 ${isDark ? "border-gray-800" : "border-gray-200"}`}>
            <MessageComposer
              onSend={sendMessage}
              disabled={isLoading}
              isStreaming={isStreaming}
              onStop={stopStreaming}
              theme={theme}
            />
          </div>

        </div>
      </div>
    </div>
  );
};

export default ChatContainer;