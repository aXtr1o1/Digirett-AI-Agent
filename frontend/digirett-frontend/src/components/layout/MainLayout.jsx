import React, { useState } from "react";
import Sidebar from "./Sidebar";
import BackgroundLayer from "../common/BackgroundLayer";
import { useTheme } from "../../providers/ThemeProvider";
import { Menu } from "lucide-react";

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

  const [isSidebarOpen, setIsSidebarOpen] = useState(() => {
    const saved = localStorage.getItem("sidebar_open");
    return saved !== null ? JSON.parse(saved) : true;
  });

  const toggleSidebar = () => {
    setIsSidebarOpen(prev => {
      const next = !prev;
      localStorage.setItem("sidebar_open", JSON.stringify(next));
      return next;
    });
  };

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
        <div 
          style={{
            width: isSidebarOpen ? "260px" : "0px",
            minWidth: isSidebarOpen ? "260px" : "0px",
            maxWidth: isSidebarOpen ? "260px" : "0px",
            opacity: isSidebarOpen ? 1 : 0,
            overflow: "hidden",
            transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
          }}
          className="relative z-10 flex-shrink-0 h-full"
        >
          <Sidebar
            conversations={conversations}
            currentConversationId={currentConversationId}
            onSelectConversation={onSelectConversation}
            onNewChat={onNewChat}
            onDeleteConversation={onDeleteConversation}
            theme={theme}
            onToggleTheme={toggleTheme}
            onCollapseSidebar={toggleSidebar}
          />
        </div>

        {/* MAIN CONTENT */}
        <div className="relative z-10 flex flex-col flex-1 min-w-0 h-full overflow-hidden">
          {/* Floating Menu Toggle Button (visible only when sidebar is closed) */}
          {!isSidebarOpen && (
            <button
              onClick={toggleSidebar}
              style={{
                position: "absolute",
                top: "16px",
                left: "16px",
                zIndex: 40,
                width: "40px",
                height: "40px",
                borderRadius: "12px",
                backgroundColor: isDark ? "rgba(30, 30, 30, 0.8)" : "rgba(255, 255, 255, 0.8)",
                border: isDark ? "1px solid rgba(42, 42, 42, 0.5)" : "1px solid rgba(229, 231, 235, 0.5)",
                color: isDark ? "#ffffff" : "#111827",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "scale(1.05)";
                e.currentTarget.style.backgroundColor = isDark ? "rgba(42, 42, 42, 0.9)" : "rgba(243, 244, 246, 0.9)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "scale(1)";
                e.currentTarget.style.backgroundColor = isDark ? "rgba(30, 30, 30, 0.8)" : "rgba(255, 255, 255, 0.8)";
              }}
            >
              <Menu size={20} />
            </button>
          )}

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
