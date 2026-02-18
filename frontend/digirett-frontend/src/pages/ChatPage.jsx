import React from "react";
import MainLayout from "../components/layout/MainLayout";
import ChatContainer from "../components/chat/ChatContainer";
import useConversations from "../hooks/useConversations";

const ChatPage = () => {
  const {
    conversations,
    isLoading,
    currentConversationId,
    createConversation,
    selectConversation,
    deleteConversation,
    handleAutoCreatedConversation,
  } = useConversations();

  // ⛔ Removed auto-select useEffect — app now starts on default empty screen
  // Users can click a conversation in the sidebar to navigate to it

  return (
    <MainLayout
      conversations={conversations}
      currentConversationId={currentConversationId}
      onSelectConversation={selectConversation}
      onNewChat={createConversation}
      onDeleteConversation={deleteConversation}
      isLoadingConversations={isLoading}
    >
      <ChatContainer
        conversationId={currentConversationId}
        onConversationCreated={handleAutoCreatedConversation}
      />
    </MainLayout>
  );
};

export default ChatPage;