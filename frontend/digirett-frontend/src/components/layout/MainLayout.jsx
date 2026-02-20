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
  const [theme, setTheme] = useState("dark");
  const isDark = theme === "dark";

  const handleToggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const hasChats = conversations && conversations.length > 0;

  return (
    <div
      className={`flex h-screen ${
        isDark
          ? "bg-black text-gray-200"
          : "bg-white text-gray-900"
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

      <div className="flex flex-col flex-1">
        <Header theme={theme} onToggleTheme={handleToggleTheme} />

      <main
        className={`flex-1 overflow-hidden ${
          isDark ? "bg-black" : "bg-gray-100"
        }`}
      >
  <div className="h-full flex flex-col w-full px-6">
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
