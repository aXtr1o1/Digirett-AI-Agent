import React from "react";
import MainLayout from "../components/layout/MainLayout";
import ChatContainer from "../components/chat/ChatContainer";
import useConversations from "../hooks/useConversations";

// TODO: once you know your auth file, replace userId={null} with userId={user?.id}
// and add the import, e.g:
//   import { useAuth } from "../providers/AuthProvider";
//   const { user } = useAuth();

const ChatPage = () => {
  const {
    conversations,
    isLoading,
    currentConversationId,
    selectConversation,
    deleteConversation,
    handleAutoCreatedConversation,
    moveConversationToTop,
    setCurrentConversationId,
  } = useConversations();

  return (
    <MainLayout
      theme="light"
      conversations={conversations}
      currentConversationId={currentConversationId}
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
        userId={null}
      />
    </MainLayout>
  );
};

export default ChatPage;
