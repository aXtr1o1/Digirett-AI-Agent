import React from "react";
import Sidebar from "./Sidebar";
import BackgroundLayer from "../common/BackgroundLayer";
import { useTheme } from "../../providers/ThemeProvider";

const MainLayout = ({
  children,
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  rightSidebar,
}) => {
  const { theme, toggleTheme, isDark } = useTheme();


  return (
    <div className="relative flex h-screen w-screen overflow-hidden">
      {/* Background Layer - Fixed behind everything (both themes) */}
      <BackgroundLayer theme={theme} />
      
      {/* Main Content Container with padding on all sides */}
      <div
        className={`relative flex h-full w-full p-2 gap-2 ${
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
            onToggleTheme={toggleTheme}
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

        {/* RIGHT SIDEBAR — only shown if provided */}
        {rightSidebar && (
          <div className="relative z-10 flex-shrink-0 h-full animate-in slide-in-from-right duration-300">
            {React.cloneElement(rightSidebar, { theme })}
          </div>
        )}
      </div>
    </div>
  );
};

export default MainLayout;
