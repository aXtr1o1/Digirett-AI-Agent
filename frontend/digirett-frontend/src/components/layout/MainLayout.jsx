import React, { useState } from "react";
import Sidebar from "./Sidebar";
import BackgroundLayer from "../common/BackgroundLayer";

// AFTER
const MainLayout = ({
  children,
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  theme: initialTheme = "light",            // ← accept prop, default light
}) => {
  const [theme, setTheme] = useState(initialTheme);  // ← use prop as initial value
  const isDark = theme === "dark";

  const handleToggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
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
