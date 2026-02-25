import React, { useRef } from "react";
import MessageList from "./MessageList";
import MessageComposer from "./MessageComposer";
import ErrorMessage from "../common/ErrorMessage";
import useChat from "../../hooks/useChat";

const ChatContainer = ({
  conversationId,
  onConversationCreated,
  moveConversationToTop,
  theme = "dark"
}) =>  {
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
  }  = useChat(
  conversationId,
  onConversationCreated,
  moveConversationToTop
);

  return (
    <div className={`flex flex-col h-full w-full bg-transparent`}>

      {error && (
        <div className="px-6 pt-4">
          <ErrorMessage message={error} onRetry={loadMessages} />
        </div>
      )}

      {/* SCROLLABLE MESSAGE AREA */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden" style={{ overscrollBehavior: 'none' }}>
        {/* ChatGPT-style: max-w-2xl centered, generous padding */}
        <div className="max-w-2xl mx-auto w-full px-4 pt-6 pb-4">
          <MessageList
            messages={messages}
            isLoading={isLoading}
            streamingMessage={streamingMessage}
            isStreaming={isStreaming}
            theme={theme}
          />
        </div>
      </div>

      {/* INPUT BAR — fixed at bottom, ChatGPT style */}
      <div className={`flex-shrink-0 bg-transparent`}>
        <div className="max-w-2xl mx-auto w-full px-4 py-4">
          <MessageComposer
            onSend={sendMessage}
            disabled={isLoading}
            isStreaming={isStreaming}
            onStop={stopStreaming}
            theme={theme}
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
