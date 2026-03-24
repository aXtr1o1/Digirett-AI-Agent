import React, { useEffect } from 'react';
import MessageList from './MessageList';
import MessageComposer from './MessageComposer';
import ErrorMessage from '../common/ErrorMessage';
import useChat from '../../hooks/useChat';

const ChatContainer = ({ conversationId, theme = 'dark' }) => {
  const {
    messages,
    isLoading,
    error,
    streamingMessage,
    isStreaming,
    sendMessage,
    loadMessages,
    stopStreaming,
  } = useChat(conversationId);

  // Load messages when conversation changes
  useEffect(() => {
    if (conversationId) {
      loadMessages();
    }
  }, [conversationId, loadMessages]);

  return (
  <div className="flex flex-col h-full bg-black">

    {/* Error */}
    {error && (
      <div className="p-4">
        <ErrorMessage message={error} onRetry={loadMessages} />
      </div>
    )}

    {/* ⭐ CENTERED CONTENT */}
    <div className="flex-1 flex justify-center overflow-hidden">
      <div className="w-full max-w-4xl flex flex-col h-full">

        <MessageList
          messages={messages}
          isLoading={isLoading}
          streamingMessage={streamingMessage}
          isStreaming={isStreaming}
        />

        <MessageComposer
          onSend={sendMessage}
          disabled={isLoading}
          isStreaming={isStreaming}
          onStop={stopStreaming}
        />

      </div>
    </div>
  </div>
);
};

export default ChatContainer;
