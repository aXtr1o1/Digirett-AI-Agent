import React, { useEffect, useRef } from "react";
import Message from "./Message";
import TypingIndicator from "./TypingIndicator";
import LoadingSpinner from "../common/LoadingSpinner";

const MessageList = ({
  messages,
  isLoading,
  streamingMessage,
  isStreaming,
  isProcessingDoc,
  theme = "dark",
  conversationId,
  conversationTitle,
}) => {
  const messagesEndRef = useRef(null);
  const isDark = theme === "dark";

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMessage, isStreaming, isProcessingDoc]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (messages.length === 0 && !isStreaming && !streamingMessage && !isProcessingDoc) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
        <h2 className={`text-4xl font-semibold mb-2 ${isDark ? "text-white" : "text-gray-900"}`}>
          Welcome to DigiRett AI
        </h2>
        <p className={`text-sm max-w-sm ${isDark ? "text-gray-400" : "text-gray-500"}`}>
          Ask me anything about Norwegian law and regulations.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full px-4 py-6">
      {/* Historical + live messages */}
      {messages.map((message) => (
        <Message
          key={message.id || Math.random()}
          message={message}
          theme={theme}
          conversationId={conversationId}
          conversationTitle={conversationTitle}
        />
      ))}

      {/* Doc processing — reuses TypingIndicator with a different label */}
      {isProcessingDoc && (
        <TypingIndicator theme={theme} label="Analysing document" />
      )}

      {/* Streaming assistant response */}
      {isStreaming && streamingMessage && (
        <Message
          message={{
            role: "assistant",
            content: streamingMessage,
          }}
          isStreaming={true}
          theme={theme}
        />
      )}

      {/* Thinking dots — text-only queries before first token */}
      {isStreaming && !streamingMessage && !isProcessingDoc && (
        <TypingIndicator theme={theme} />
      )}

      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;