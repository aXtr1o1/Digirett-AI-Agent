import React, { useEffect, useRef } from 'react';
import Message from './Message';
import TypingIndicator from './TypingIndicator';
import LoadingSpinner from '../common/LoadingSpinner';
import { Bot } from 'lucide-react';

const MessageList = ({ messages, isLoading, streamingMessage, isStreaming }) => {
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMessage]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (messages.length === 0 && !streamingMessage) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4">
        <Bot className="h-16 w-16 text-gray-300 mb-4" />
        <h2 className="text-2xl font-semibold text-gray-700 mb-2">
          Welcome to DigiRett
        </h2>
        <p className="text-gray-500 max-w-md">
          Your Norwegian Legal AI Assistant. Ask me anything about Norwegian law and regulations.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {messages.map((message, index) => (
        <Message key={index} message={message} />
      ))}

      {/* Streaming message */}
      {isStreaming && streamingMessage && (
        <Message
          message={{
            role: 'assistant',
            content: streamingMessage,
          }}
          isStreaming={true}
        />
      )}

      {/* Typing indicator */}
      {isStreaming && !streamingMessage && (
        <TypingIndicator />
      )}

      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;
