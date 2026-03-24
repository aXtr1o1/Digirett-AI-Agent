import React from "react";
import MainLayout from "../components/layout/MainLayout";
import ChatContainer from "../components/chat/ChatContainer";
import useConversations from "../hooks/useConversations";

const ChatPage = () => {

  const {
    conversations,
    isLoading,
    currentConversationId,
    selectConversation,
    deleteConversation,
    handleAutoCreatedConversation,
    moveConversationToTop,
    setCurrentConversationId
  } = useConversations();

  return (
    <MainLayout
      conversations={conversations}
      currentConversationId={currentConversationId}

      // ✅ Clicking New Chat only opens empty welcome page
      onNewChat={() => {
        localStorage.removeItem("conversationId");
        setCurrentConversationId(null);
      }}

      onSelectConversation={selectConversation}
      onDeleteConversation={deleteConversation}
      isLoadingConversations={isLoading}
    >
      <ChatContainer
        conversationId={currentConversationId}
        onConversationCreated={handleAutoCreatedConversation}
        moveConversationToTop={moveConversationToTop}
      />
    </MainLayout>
  );
};

export default ChatPage;