import React from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import useConversations from "../../hooks/useConversations";

const MainLayout = ({ children }) => {
  // ⭐ get conversations
  const { conversations } = useConversations();

  // ⭐ check if chats exist
  const hasChats = conversations.length > 0;

  return (
    <div className="flex h-screen bg-black text-white overflow-hidden">

      <Sidebar />

      {/* RIGHT CONTENT */}
      <div className="flex flex-col flex-1">

        <Header />

        <main className="flex-1 overflow-hidden flex justify-center">
          <div
            className={`h-full flex flex-col ${
              hasChats ? "w-full max-w-5xl" : "w-full"
            }`}
          >
            {children}
          </div>
        </main>

      </div>
    </div>
  );
};

export default MainLayout;
