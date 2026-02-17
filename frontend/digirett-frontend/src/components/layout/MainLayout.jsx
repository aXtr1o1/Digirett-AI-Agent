import React, { useState } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";

const MainLayout = ({
  children,
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
}) => {
  // ⭐ Theme state lives here and is passed down
  const [theme, setTheme] = useState("dark");
  const isDark = theme === "dark";

  const handleToggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  // ⭐ check if chats exist
  const hasChats = conversations && conversations.length > 0;

  return (
    <div
      className={`flex h-screen overflow-hidden transition-colors duration-300 ${
        isDark ? "bg-black text-white" : "bg-gray-50 text-gray-900"
      }`}
    >
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={onSelectConversation}
        onNewChat={onNewChat}
        onDeleteConversation={onDeleteConversation}
        theme={theme}
      />

      {/* RIGHT CONTENT */}
      <div className="flex flex-col flex-1">
        <Header theme={theme} onToggleTheme={handleToggleTheme} />

        <main className="flex-1 overflow-hidden flex justify-center">
          <div
            className={`h-full flex flex-col ${
              hasChats ? "w-full max-w-5xl" : "w-full"
            }`}
          >
            {/* Clone children and inject theme prop */}
            {React.Children.map(children, (child) =>
              React.isValidElement(child)
                ? React.cloneElement(child, { theme })
                : child
            )}
          </div>
        </main>
      </div>
    </div>
  );
};

export default MainLayout;