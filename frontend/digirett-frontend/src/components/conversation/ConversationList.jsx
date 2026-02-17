import React from 'react';
import ConversationItem from './ConversationItem';
import LoadingSpinner from '../common/LoadingSpinner';

const ConversationList = ({ 
  conversations, 
  currentConversationId, 
  onSelectConversation,
  onDeleteConversation,
  isLoading 
}) => {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <LoadingSpinner />
      </div>
    );
  }

  if (!conversations || conversations.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
        <p className="text-sm text-gray-500">No conversations yet</p>
        <p className="text-xs text-gray-400 mt-1">
          Click "New Chat" to start
        </p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-gray-200">
      {conversations.map((conversation) => (
        <ConversationItem
          key={conversation.id || conversation.conversation_id}
          conversation={conversation}
          isActive={
            (conversation.id || conversation.conversation_id) === currentConversationId
          }
          onClick={() => onSelectConversation(
            conversation.id || conversation.conversation_id
          )}
          onDelete={onDeleteConversation}
        />
      ))}
    </div>
  );
};

export default ConversationList;
