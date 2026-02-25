import React, { useState } from "react";
import Sidebar from "./Sidebar";
import BackgroundLayer from "../common/BackgroundLayer";

const MainLayout = ({
  children,
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
}) => {
  // ✅ FIX: Read saved theme from localStorage on first load, fallback to "dark"
  const [theme, setTheme] = useState(
    () => localStorage.getItem("theme") || "dark"
  );
  const isDark = theme === "dark";

  const handleToggleTheme = () => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      // ✅ FIX: Save new theme to localStorage whenever it changes
      localStorage.setItem("theme", next);
      return next;
    });
  };

  return (
    <div className="relative flex h-screen w-screen overflow-hidden">
      {/* Background Layer - Fixed behind everything (both themes) */}
      <BackgroundLayer theme={theme} />
      
      {/* Main Content Container with padding on all sides */}
      <div
        className={`relative flex h-full w-full p-2 ${
          isDark ? "text-gray-200" : "text-gray-900"
        }`}
      >
        {/* SIDEBAR — fixed, never shrinks */}
        <div className="relative z-10 flex-shrink-0 h-full">
          <Sidebar
            conversations={conversations}
            currentConversationId={currentConversationId}
            onSelectConversation={onSelectConversation}
            onNewChat={onNewChat}
            onDeleteConversation={onDeleteConversation}
            theme={theme}
            onToggleTheme={handleToggleTheme}
          />
        </div>

        {/* MAIN CONTENT */}
        <div className="relative z-10 flex flex-col flex-1 min-w-0 h-full overflow-hidden">
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
    </div>
  );
};

export default MainLayout;
