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
  const [theme, setTheme] = useState("light");
  const isDark = theme === "dark";

  const handleToggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  return (
    <div
      className={`flex h-screen w-screen overflow-hidden ${
        isDark ? "bg-[#212121] text-gray-200" : "bg-white text-gray-900"
      }`}
    >
      {/* SIDEBAR — fixed, never shrinks */}
      <div className="flex-shrink-0 h-full">
        <Sidebar
          conversations={conversations}
          currentConversationId={currentConversationId}
          onSelectConversation={onSelectConversation}
          onNewChat={onNewChat}
          onDeleteConversation={onDeleteConversation}
          theme={theme}
        />
      </div>

      {/* MAIN CONTENT */}
      <div className="flex flex-col flex-1 min-w-0 h-full overflow-hidden">
        <Header theme={theme} onToggleTheme={handleToggleTheme} />

        <main className="flex-1 overflow-hidden min-w-0">
          <div className="h-full w-full">
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
