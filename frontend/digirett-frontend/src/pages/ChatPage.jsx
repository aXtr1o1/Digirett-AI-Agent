import React from "react";
import MainLayout from "../components/layout/MainLayout";
import ChatContainer from "../components/chat/ChatContainer";
import useConversations from "../hooks/useConversations";
import { useUser } from "@clerk/clerk-react";

const ChatPage = () => {
  const { user } = useUser();
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
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center h-full text-gray-500">
          Loading...
        </div>
      ) : (
        <ChatContainer
          conversationId={currentConversationId}
          onConversationCreated={handleAutoCreatedConversation}
          moveConversationToTop={moveConversationToTop}
          userId={user?.id}
        />
      )}
    </MainLayout>
  );
};

export default ChatPage;
