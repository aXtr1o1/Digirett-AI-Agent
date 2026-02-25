import React, { useEffect, useRef } from "react";
import Message from "./Message";
import TypingIndicator from "./TypingIndicator";
import LoadingSpinner from "../common/LoadingSpinner";
import GlowingOrb from "../common/GlowingOrb";

const MessageList = ({
  messages,
  isLoading,
  streamingMessage,
  isStreaming,
  theme = "dark",
}) => {
  const messagesEndRef = useRef(null);
  const isDark = theme === "dark";

  // 🔥 Auto-scroll on new messages OR streaming updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMessage, isStreaming]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  // ✅ Welcome Screen (only when nothing exists)
  if (messages.length === 0 && !isStreaming && !streamingMessage) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
        {/* Glowing Orb */}
        {/* <div style={{ marginBottom: "32px" }}>
          <GlowingOrb theme={theme} size={80} />
        </div> */}
        
        <h2 className={`text-2xl font-semibold mb-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
          Welcome to DigiRett AI
        </h2>

        <p
          className={`text-sm max-w-sm ${
            isDark ? "text-gray-400" : "text-gray-500"
          }`}
        >
          Ask me anything about Norwegian law and regulations.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full px-4 py-6">
      {/* Existing Messages */}
      {messages.map((message) => (
        <Message
          key={message.id || Math.random()}
          message={message}
          theme={theme}
        />
      ))}

      {/* 🔥 Streaming Assistant Message */}
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

      {/* 🧠 Thinking State (Before First Token) */}
      {isStreaming && !streamingMessage && (
        <TypingIndicator theme={theme} />
      )}

      {/* Scroll Anchor */}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;