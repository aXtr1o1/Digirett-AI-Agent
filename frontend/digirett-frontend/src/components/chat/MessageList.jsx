import React, { useEffect, useRef } from 'react';
import Message from './Message';
import TypingIndicator from './TypingIndicator';
import LoadingSpinner from '../common/LoadingSpinner';
import { Bot } from 'lucide-react';

const MessageList = ({ messages, isLoading, streamingMessage, isStreaming, theme = 'dark' }) => {
  const messagesEndRef = useRef(null);
  const isDark = theme === 'dark';

useEffect(() => {
  messagesEndRef.current?.scrollIntoView({ behavior: 'instant' });
}, [messages]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (messages.length === 0 && !streamingMessage) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <div className={`h-16 w-16 rounded-full flex items-center justify-center mb-5 ${
        isDark ? 'bg-white' : 'bg-gray-900'
      }`}>
        <Bot className={`h-10 w-10 ${isDark ? 'text-black' : 'text-white'}`} />
      </div>
        <h2 className={`text-2xl font-semibold mb-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
          Welcome to DigiRett AI
        </h2>
        <p className={`text-sm max-w-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
          Ask me anything about Norwegian law and regulations.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full">
      {messages.map((message) => (
        <Message key={message.id} message={message} theme={theme} />
      ))}

      {isStreaming && streamingMessage && (
        <Message
          message={{ role: 'assistant', content: streamingMessage }}
          isStreaming={true}
          theme={theme}
        />
      )}

      {isStreaming && !streamingMessage && (
        <TypingIndicator theme={theme} />
      )}

      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;
