import React, { useEffect } from 'react';
import MainLayout from '../components/layout/MainLayout';
import ChatContainer from '../components/chat/ChatContainer';
import useConversations from '../hooks/useConversations';

const ChatPage = () => {
  const {
    conversations,
    isLoading,
    currentConversationId,
    createConversation,
    selectConversation,
    deleteConversation,
  } = useConversations();

  useEffect(() => {
    if (!currentConversationId && conversations.length > 0) {
      selectConversation(conversations[0].id);
    }
  }, [currentConversationId, conversations, selectConversation]);

  const handleNewChat = async () => {
    await createConversation();
  };

  const handleDeleteChat = async (conversationId) => {
    await deleteConversation(conversationId);
  };

  return (
    <MainLayout
      conversations={conversations}
      currentConversationId={currentConversationId}
      onSelectConversation={selectConversation}
      onNewChat={handleNewChat}
      onDeleteConversation={handleDeleteChat}
      isLoadingConversations={isLoading}
    >
    <ChatContainer conversationId={currentConversationId} />
    </MainLayout>
  );
};

export default ChatPage;
