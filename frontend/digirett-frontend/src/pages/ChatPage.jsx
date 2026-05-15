import React, { useState } from "react";
import MainLayout from "../components/layout/MainLayout";
import ChatContainer from "../components/chat/ChatContainer";
import LegalPanel from "../components/layout/LegalPanel";
import useConversations from "../hooks/useConversations";
import { useUser } from "@clerk/clerk-react";

const ChatPage = () => {
  const { user } = useUser();
  const [isEscalated, setIsEscalated] = useState(false);
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
        setIsEscalated(false);
      }}
      onSelectConversation={(id) => {
        selectConversation(id);
        setIsEscalated(false);
      }}
      onDeleteConversation={deleteConversation}
      isLoadingConversations={isLoading}
      rightSidebar={
        isEscalated && currentConversationId ? (
          <LegalPanel conversationId={currentConversationId} />
        ) : null
      }
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
          onEscalated={setIsEscalated}
        />
      )}
    </MainLayout>
  );
};

export default ChatPage;
