import React, { useState, useEffect, useRef } from "react";
import {
  Plus,
  MessageSquare,
  Archive,
  Menu,
  PanelLeftClose,
  FolderPlus,
  Image as ImageIcon,
  FileText,
  Search,
  Trash2,
  Sun,
  Moon,
  LogOut,
  User,
  Shield,
  Gavel,
  AlertTriangle,
  MoreHorizontal,
  Bookmark,
  X
} from "lucide-react";
import { useUser, useClerk } from "@clerk/clerk-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import hitlService from "../../services/hitlService";
import conversationService from "../../services/conversationService";
import libraryService from "../../services/libraryService";
import { getSupabaseClient } from "../../lib/supabase";
import UpgradeCard from "../common/UpgradeCard";
import QuotaPanel from "../chat/QuotaPanel";
import LibraryPanel from "../chat/LibraryPanel";

const Sidebar = ({
  conversations,
  currentConversationId,
  archivedIds = [],
  archiveConversation,
  restoreConversation,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  theme = "dark",
  onToggleTheme,
  onCollapseSidebar,
}) => {
  const isDark = theme === "dark";
  const [activeFeature, setActiveFeature] = useState("chat");
  const [activeWorkspace, setActiveWorkspace] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);
  const [openMenuId, setOpenMenuId] = useState(null);
  const [savingConvId, setSavingConvId] = useState(null); // tracks which conv is being saved to library
  const [libraryFilterConvId, setLibraryFilterConvId] = useState(null);
  const [sidebarSearchQuery, setSidebarSearchQuery] = useState("");
  const [searchParams] = useSearchParams();
  const activeView = searchParams.get("view"); // "library" or null
  const { getToken } = useAuth();

  // Sync activeFeature with URL view param
  useEffect(() => {
    if (activeView === "library") {
      setActiveFeature("library");
    } else if (activeFeature === "library") {
      setActiveFeature("chat");
    }
  }, [activeView]);

  const handleArchive = (id) => {
    if (archiveConversation) archiveConversation(id);
    setOpenMenuId(null);
    if (id === currentConversationId) {
      if (onNewChat) onNewChat();
    }
  };

  const handleRestore = (id) => {
    if (restoreConversation) restoreConversation(id);
    setOpenMenuId(null);
    if (id === currentConversationId) {
      if (onNewChat) onNewChat();
    }
  };

  /**
   * Save all messages (user and AI) from a conversation to the Library, then navigate to Library.
   */
  const handleSaveConversationToLibrary = async (conversationId) => {
    setSavingConvId(conversationId);
    setOpenMenuId(null);
    try {
      // Fetch messages using conversationService to avoid Clerk token / Supabase RLS issues
      const data = await conversationService.getConversationWithMessages(conversationId);
      const conversationMessages = data?.messages || [];

      // Save each message to library (skips already-saved ones via upsert)
      for (const msg of conversationMessages) {
        if (!msg.message_id) continue;
        await libraryService.saveMessage({
          id: msg.message_id,
          message_id: msg.message_id,
          content: msg.content,
          role: msg.role,
          sources: msg.sources,
          metadata: msg.metadata
        });
      }

      // Navigate to library
      navigate("/chat?view=library");
    } catch (err) {
      console.error("[Sidebar] Failed to save conversation to library:", err);
      // Still navigate to library even on error
      navigate("/chat?view=library");
    } finally {
      setSavingConvId(null);
    }
  };

  const { user } = useUser();
  const { signOut } = useClerk();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await signOut();
    navigate("/sign-in");
  };

  const displayName = user?.username || user?.primaryEmailAddress?.emailAddress || "User";

  // Close menus when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
      if (openMenuId && !event.target.closest(".conv-menu-container")) {
        setOpenMenuId(null);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [menuOpen, openMenuId]);

  const handleEscalate = () => {
    // This is a placeholder for now to avoid the crash.
    // In a real scenario, this would trigger the HITL escalation.
    // Since escalation is per-conversation, we might want to just navigate to chat
    // or show a toast if no conversation is active.
    alert("To talk to a lawyer, please open a conversation and click the 'Talk to Lawyer' icon in the chat box.");
  };

  const role = user?.publicMetadata?.role || "user";

  const features = [
    { id: "chat", label: "Chat", icon: MessageSquare, path: "/chat" },
    { id: "archived", label: "Archived", icon: Archive },
    { id: "library", label: "Library", icon: Bookmark },
  ];

  if (role === "admin" || role === "system_admin") {
    features.push({
      id: "admin",
      label: role === "system_admin" ? "System Admin Dashboard" : "Admin Dashboard",
      icon: Shield,
      path: "/admin"
    });
  }
  if (role === "lawyer") {
    features.push({ id: "lawyer", label: "Lawyer Dashboard", icon: FileText, path: "/lawyer" });
  }

  const handleFeatureClick = (feature) => {
    if (feature.id === "escalate") {
      handleEscalate();
      return;
    }
    setActiveFeature(feature.id);

    if (feature.id === "library") {
      // Navigate to library full-page view
      navigate("/chat?view=library");
      return;
    }

    // Prevent displaying a mismatched conversation when toggling tabs
    if (feature.id === "chat") {
      if (currentConversationId && archivedIds.includes(currentConversationId)) {
        if (onNewChat) onNewChat();
      }
      // Clear ?view param if set
      if (!window.location.pathname.startsWith("/chat")) {
        navigate("/chat");
      } else {
        navigate("/chat", { replace: true });
      }
      return;
    } else if (feature.id === "archived") {
      if (currentConversationId && !archivedIds.includes(currentConversationId)) {
        if (onNewChat) onNewChat();
      }
    }

    if (feature.path) {
      navigate(feature.path);
    } else {
      if (!window.location.pathname.startsWith("/chat")) {
        navigate("/chat");
      }
    }
  };

  const activeConversations = (conversations || []).filter(c => !archivedIds.includes(c.conversation_id));
  const archivedConversations = (conversations || []).filter(c => archivedIds.includes(c.conversation_id));
  
  // Filter conversations by search query if provided
  const filterConversations = (list) => {
    if (!sidebarSearchQuery.trim()) return list;
    const q = sidebarSearchQuery.toLowerCase();
    return list.filter(c => (c.title || "New Conversation").toLowerCase().includes(q));
  };

  // Library view shows the regular chat list in the sidebar (Library is a main-content view)
  const displayedConversations = filterConversations(
    activeFeature === "archived" ? archivedConversations : activeConversations
  );

  return (
    <aside
      style={{
        width: "260px",
        minWidth: "260px",
        maxWidth: "260px",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: isDark
          ? "rgba(17, 17, 17, 0.5)"
          : "rgba(250, 250, 250, 0.6)",
        borderRight: isDark
          ? "1px solid rgba(42, 42, 42, 0.4)"
          : "1px solid rgba(229, 231, 235, 0.4)",
        borderTopLeftRadius: "16px",
        borderTopRightRadius: "16px",
        borderBottomLeftRadius: "16px",
        borderBottomRightRadius: "16px",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        overflow: "hidden",
        height: "calc(100% - 16px)",
        marginTop: "8px",
        marginBottom: "8px",
      }}
    >
      {/* APP BRANDING with Hamburger Menu & User Profile */}
      <div style={{
        padding: "20px 16px 16px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "10px",
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flex: 1 }}>
          <div
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "50%",
              backgroundColor: isDark ? "#3B82F6" : "#2563EB",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#ffffff",
              fontSize: "18px",
              fontWeight: "700",
              flexShrink: 0,
            }}
          >
            <img src="/digirett-logo.png" alt="DigiRett Logo" style={{ width: "32px", height: "32px" }} />
          </div>
          <span style={{
            fontSize: "16px",
            fontWeight: "600",
            color: isDark ? "#ffffff" : "#111827",
          }}>
            DigiRett
          </span>
        </div>

        {/* Controls: Profile Avatar & Hamburger Collapse Button */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          {/* User Profile Avatar */}
          <div ref={menuRef} style={{ position: "relative" }}>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "50%",
                backgroundColor: "transparent",
                border: "none",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                overflow: "hidden",
                transition: "all 0.2s",
                border: isDark ? "1px solid rgba(255, 255, 255, 0.1)" : "1px solid rgba(0, 0, 0, 0.1)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "scale(1.05)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "scale(1)";
              }}
              title="User Account"
            >
              {user?.imageUrl ? (
                <img src={user.imageUrl} alt="Profile" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <div style={{
                  width: "100%",
                  height: "100%",
                  backgroundColor: isDark ? "rgba(59, 130, 246, 0.2)" : "rgba(59, 130, 246, 0.15)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: isDark ? "#3B82F6" : "#2563EB",
                }}>
                  <User size={16} />
                </div>
              )}
            </button>

            {/* Dropdown Menu */}
            {menuOpen && (
              <div
                style={{
                  position: "absolute",
                  top: "100%",
                  right: 0,
                  marginTop: "8px",
                  width: "180px",
                  borderRadius: "12px",
                  backgroundColor: isDark
                    ? "rgba(26, 26, 26, 0.95)"
                    : "rgba(255, 255, 255, 0.95)",
                  border: isDark
                    ? "1px solid rgba(42, 42, 42, 0.5)"
                    : "1px solid rgba(229, 231, 235, 0.5)",
                  backdropFilter: "blur(20px)",
                  WebkitBackdropFilter: "blur(20px)",
                  boxShadow: "0 4px 20px rgba(0, 0, 0, 0.3)",
                  zIndex: 1000,
                  overflow: "hidden",
                }}
              >
                {/* User Profile Section */}
                <div
                  style={{
                    padding: "16px",
                    borderBottom: isDark
                      ? "1px solid rgba(42, 42, 42, 0.5)"
                      : "1px solid rgba(229, 231, 235, 0.5)",
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                  }}
                >
                  <div
                    style={{
                      width: "40px",
                      height: "40px",
                      borderRadius: "50%",
                      backgroundColor: isDark
                        ? "rgba(59, 130, 246, 0.2)"
                        : "rgba(59, 130, 246, 0.15)",
                      border: isDark
                        ? "2px solid rgba(59, 130, 246, 0.4)"
                        : "2px solid rgba(59, 130, 246, 0.3)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: isDark ? "#3B82F6" : "#2563EB",
                      flexShrink: 0,
                      overflow: "hidden",
                    }}
                  >
                    {user?.imageUrl ? (
                      <img src={user.imageUrl} alt="Profile" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                    ) : (
                      <User size={20} />
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: "14px",
                      fontWeight: "600",
                      color: isDark ? "#ffffff" : "#111827",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }} title={displayName}>
                      {displayName}
                    </div>
                  </div>
                </div>

                {/* Divider */}
                <div style={{
                  height: "1px",
                  backgroundColor: isDark
                    ? "rgba(42, 42, 42, 0.5)"
                    : "rgba(229, 231, 235, 0.5)",
                  margin: "0",
                }} />

                {/* Theme Toggle */}
                <button
                  onClick={() => {
                    if (onToggleTheme) onToggleTheme();
                    setMenuOpen(false);
                  }}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                    padding: "12px 16px",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    color: isDark ? "#ffffff" : "#111827",
                    fontSize: "14px",
                    transition: "background-color 0.2s",
                    textAlign: "left",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = isDark
                      ? "rgba(42, 42, 42, 0.5)"
                      : "rgba(243, 244, 246, 0.8)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "transparent";
                  }}
                >
                  {isDark ? (
                    <>
                      <Sun size={18} />
                      <span>Light Mode</span>
                    </>
                  ) : (
                    <>
                      <Moon size={18} />
                      <span>Dark Mode</span>
                    </>
                  )}
                </button>

                {/* Divider */}
                <div style={{
                  height: "1px",
                  backgroundColor: isDark
                    ? "rgba(42, 42, 42, 0.5)"
                    : "rgba(229, 231, 235, 0.5)",
                  margin: "4px 0",
                }} />

                {/* Logout Button */}
                <button
                  onClick={handleLogout}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                    padding: "12px 16px",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    color: "#ef4444",
                    fontSize: "14px",
                    transition: "background-color 0.2s",
                    textAlign: "left",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = isDark
                      ? "rgba(239, 68, 68, 0.1)"
                      : "rgba(239, 68, 68, 0.05)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "transparent";
                  }}
                >
                  <LogOut size={18} />
                  <span>Logout</span>
                </button>
              </div>
            )}
          </div>

          {/* Hamburger Menu Close Button */}
          <button
            onClick={onCollapseSidebar}
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "8px",
              backgroundColor: "transparent",
              border: "none",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: isDark ? "#ffffff" : "#111827",
              transition: "all 0.2s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = isDark
                ? "rgba(42, 42, 42, 0.5)"
                : "rgba(243, 244, 246, 0.8)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "transparent";
            }}
            title="Collapse Sidebar"
          >
            <PanelLeftClose size={20} />
          </button>
        </div>
      </div>

      {/* NEW CHAT BUTTON */}
      <div style={{ padding: "0 12px 16px", flexShrink: 0 }}>
        <button
          onClick={onNewChat}
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "12px 16px",
            borderRadius: "12px",
            fontSize: "14px",
            fontWeight: "500",
            backgroundColor: isDark
              ? "rgba(26, 26, 26, 0.8)"
              : "rgba(255, 255, 255, 0.8)",
            color: isDark ? "#ffffff" : "#111827",
            border: isDark
              ? "1px solid rgba(42, 42, 42, 0.5)"
              : "1px solid rgba(229, 231, 235, 0.5)",
            cursor: "pointer",
            transition: "all 0.2s",
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = isDark
              ? "rgba(59, 130, 246, 0.2)"
              : "rgba(59, 130, 246, 0.1)";
            e.currentTarget.style.borderColor = isDark
              ? "rgba(59, 130, 246, 0.5)"
              : "rgba(59, 130, 246, 0.3)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = isDark
              ? "rgba(26, 26, 26, 0.8)"
              : "rgba(255, 255, 255, 0.8)";
            e.currentTarget.style.borderColor = isDark
              ? "rgba(42, 42, 42, 0.5)"
              : "rgba(229, 231, 235, 0.5)";
          }}
        >
          <Plus size={18} style={{ flexShrink: 0 }} />
          <MessageSquare size={16} style={{ flexShrink: 0 }} />
          <span>New Chat</span>
        </button>
      </div>

      {/* ── SCROLLABLE MIDDLE SECTION ─────────────────────────────────────
           Everything between New Chat and Beta Version lives here.
           One scroll area = no space competition between QuotaPanel + Features + Conv list.
      ──────────────────────────────────────────────────────────────────── */}
      <div
        className="sidebar-scrollbar-hidden"
        style={{
          flex: 1,
          overflowY: "auto",
          overflowX: "hidden",
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          scrollbarWidth: "none",
          msOverflowStyle: "none",
        }}
      >

        {/* QUOTA PANEL — top of scrollable area */}
        {activeFeature === "chat" && (
          <QuotaPanel
            conversationId={currentConversationId}
            isDark={isDark}
          />
        )}

        {/* SEARCH HISTORY INPUT */}
        {(activeFeature === "chat" || activeFeature === "archived" || activeFeature === "library") && (
          <div style={{ padding: "4px 8px", flexShrink: 0 }}>
            <div style={{ margin: "0 8px 8px", position: "relative" }}>
              <Search
                size={12}
                style={{
                  position: "absolute",
                  left: "10px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: isDark ? "#6b7280" : "#9ca3af",
                  pointerEvents: "none",
                }}
              />
              <input
                type="text"
                placeholder="Search history..."
                value={sidebarSearchQuery}
                onChange={(e) => setSidebarSearchQuery(e.target.value)}
                style={{
                  width: "100%",
                  padding: "6px 24px 6px 26px",
                  borderRadius: "8px",
                  fontSize: "12px",
                  backgroundColor: isDark ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.03)",
                  color: isDark ? "#ffffff" : "#111827",
                  border: isDark ? "1px solid rgba(255, 255, 255, 0.08)" : "1px solid rgba(0, 0, 0, 0.08)",
                  outline: "none",
                  transition: "border-color 0.15s",
                  boxSizing: "border-box",
                }}
                onFocus={(e) => (e.target.style.borderColor = "#3b82f6")}
                onBlur={(e) => (e.target.style.borderColor = isDark ? "rgba(255, 255, 255, 0.08)" : "rgba(0, 0, 0, 0.08)")}
              />
              {sidebarSearchQuery && (
                <button
                  onClick={() => setSidebarSearchQuery("")}
                  style={{
                    position: "absolute",
                    right: "6px",
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: isDark ? "#6b7280" : "#9ca3af",
                    padding: "2px",
                    display: "flex",
                  }}
                >
                  <X size={10} />
                </button>
              )}
            </div>
          </div>
        )}

        {/* FEATURES SECTION */}
        <div style={{ flexShrink: 0, marginBottom: "8px" }}>
          <div style={{
            padding: "0 16px 8px",
            fontSize: "11px",
            fontWeight: "600",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: isDark ? "#6b7280" : "#9ca3af",
          }}>
            Features
          </div>
          <div style={{ padding: "4px 8px" }}>
            {features.map((feature) => {
              const Icon = feature.icon;
              const isActive = activeFeature === feature.id;
              return (
                <button
                  key={feature.id}
                  onClick={() => {
                    handleFeatureClick(feature);
                  }}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    padding: "10px 12px",
                    borderRadius: "10px",
                    fontSize: "13px",
                    fontWeight: "500",
                    backgroundColor: isActive
                      ? isDark
                        ? "rgba(59, 130, 246, 0.15)"
                        : "rgba(59, 130, 246, 0.1)"
                      : "transparent",
                    color: isActive
                      ? isDark ? "#3B82F6" : "#2563EB"
                      : isDark ? "#d1d5db" : "#374151",
                    border: "none",
                    cursor: "pointer",
                    transition: "all 0.15s",
                    textAlign: "left",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.backgroundColor = isDark
                        ? "rgba(42, 42, 42, 0.5)"
                        : "rgba(243, 244, 246, 0.8)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.backgroundColor = "transparent";
                    }
                  }}
                >
                  <Icon
                    size={16}
                    style={{
                      flexShrink: 0,
                      color: isActive
                        ? (isDark ? "#3B82F6" : "#2563EB")
                        : (isDark ? "#d1d5db" : "#374151")
                    }}
                  />
                  <span>{feature.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* CHAT HISTORY (always visible; shows chat list for chat+library, archived list for archived) */}
        {(activeFeature === "chat" || activeFeature === "archived" || activeFeature === "library") && (
          <div
            style={{
              padding: "4px 8px",
              display: "flex",
              flexDirection: "column",
              gap: "4px",
            }}>

            {displayedConversations.length === 0 ? (
              <div style={{
                padding: "16px 12px",
                textAlign: "center",
                fontSize: "12px",
                color: isDark ? "#6b7280" : "#9ca3af",
              }}>
                {activeFeature === "archived" ? "No archived conversations yet" : "No conversations yet"}
              </div>
            ) : (
              displayedConversations.map((c) => (
                <div
                  key={c.conversation_id}
                  onClick={() => onSelectConversation(c.conversation_id)}
                  style={{
                    position: "relative",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "8px",
                    padding: "10px 12px",
                    borderRadius: "10px",
                    cursor: "pointer",
                    marginBottom: "2px",
                    backgroundColor:
                      c.conversation_id === currentConversationId
                        ? isDark
                          ? "rgba(59, 130, 246, 0.15)"
                          : "rgba(59, 130, 246, 0.1)"
                        : "transparent",
                    color: c.conversation_id === currentConversationId
                      ? isDark ? "#3B82F6" : "#2563EB"
                      : isDark ? "#d1d5db" : "#374151",
                    transition: "all 0.15s",
                  }}
                  onMouseEnter={(e) => {
                    if (c.conversation_id !== currentConversationId) {
                      e.currentTarget.style.backgroundColor = isDark
                        ? "rgba(42, 42, 42, 0.5)"
                        : "rgba(243, 244, 246, 0.8)";
                    }
                    const optionsButton = e.currentTarget.querySelector(".options-btn");
                    if (optionsButton) optionsButton.style.opacity = "1";
                  }}
                  onMouseLeave={(e) => {
                    if (c.conversation_id !== currentConversationId) {
                      e.currentTarget.style.backgroundColor = "transparent";
                    }
                    const optionsButton = e.currentTarget.querySelector(".options-btn");
                    if (optionsButton) optionsButton.style.opacity = "0";
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0, flex: 1 }}>
                    <MessageSquare size={13} style={{
                      flexShrink: 0, color: c.conversation_id === currentConversationId
                        ? (isDark ? "#3B82F6" : "#2563EB")
                        : (isDark ? "#6b7280" : "#9ca3af")
                    }} />
                    <span style={{
                      fontSize: "13px",
                      lineHeight: "1.4",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}>
                      {c.title || "New Conversation"}
                    </span>
                  </div>

                  <div
                    className="conv-menu-container"
                    style={{ position: "relative" }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      className="options-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenMenuId(openMenuId === c.conversation_id ? null : c.conversation_id);
                      }}
                      style={{
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        padding: "4px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: isDark ? "#9ca3af" : "#6b7280",
                        borderRadius: "6px",
                        opacity: openMenuId === c.conversation_id ? 1 : 0,
                        transition: "opacity 0.15s, background-color 0.15s, color 0.15s",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.05)";
                        e.currentTarget.style.color = isDark ? "#ffffff" : "#111827";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = "transparent";
                        e.currentTarget.style.color = isDark ? "#9ca3af" : "#6b7280";
                      }}
                      title="Options"
                    >
                      <MoreHorizontal size={14} />
                    </button>

                    {openMenuId === c.conversation_id && (
                      <div
                        style={{
                          position: "absolute",
                          top: "100%",
                          right: 0,
                          marginTop: "4px",
                          width: "140px",
                          borderRadius: "8px",
                          backgroundColor: isDark ? "rgba(26, 26, 26, 0.98)" : "rgba(255, 255, 255, 0.98)",
                          border: isDark ? "1px solid rgba(255, 255, 255, 0.08)" : "1px solid rgba(0, 0, 0, 0.08)",
                          backdropFilter: "blur(12px)",
                          WebkitBackdropFilter: "blur(12px)",
                          boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.2)",
                          zIndex: 100,
                          padding: "4px 0",
                        }}
                      >
                        {activeFeature === "chat" ? (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleArchive(c.conversation_id);
                            }}
                            style={{
                              width: "100%",
                              padding: "8px 12px",
                              fontSize: "12px",
                              textAlign: "left",
                              background: "none",
                              border: "none",
                              color: isDark ? "#d1d5db" : "#374151",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              gap: "8px",
                            }}
                            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.03)")}
                            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                          >
                            <Archive size={12} />
                            <span>Archive</span>
                          </button>
                        ) : (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRestore(c.conversation_id);
                            }}
                            style={{
                              width: "100%",
                              padding: "8px 12px",
                              fontSize: "12px",
                              textAlign: "left",
                              background: "none",
                              border: "none",
                              color: isDark ? "#d1d5db" : "#374151",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              gap: "8px",
                            }}
                            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.03)")}
                            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                          >
                            <Archive size={12} />
                            <span>Restore</span>
                          </button>
                        )}

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSaveConversationToLibrary(c.conversation_id);
                          }}
                          style={{
                            width: "100%",
                            padding: "8px 12px",
                            fontSize: "12px",
                            textAlign: "left",
                            background: "none",
                            border: "none",
                            color: savingConvId === c.conversation_id
                              ? (isDark ? "#3b82f6" : "#2563eb")
                              : (isDark ? "#d1d5db" : "#374151"),
                            cursor: savingConvId === c.conversation_id ? "not-allowed" : "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: "8px",
                            opacity: savingConvId === c.conversation_id ? 0.7 : 1,
                          }}
                          disabled={savingConvId === c.conversation_id}
                          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.03)")}
                          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                        >
                          <Bookmark size={12} />
                          <span>{savingConvId === c.conversation_id ? "Saving..." : "Save to Library"}</span>
                        </button>

                        <hr style={{ border: 0, borderTop: isDark ? "1px solid rgba(255,255,255,0.05)" : "1px solid rgba(0,0,0,0.05)", margin: "4px 0" }} />

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteConversation(c.conversation_id);
                            setOpenMenuId(null);
                          }}
                          style={{
                            width: "100%",
                            padding: "8px 12px",
                            fontSize: "12px",
                            textAlign: "left",
                            background: "none",
                            border: "none",
                            color: "#ef4444",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: "8px",
                          }}
                          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = isDark ? "rgba(239, 68, 68, 0.08)" : "rgba(239, 68, 68, 0.04)")}
                          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                        >
                          <Trash2 size={12} />
                          <span>Delete</span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

      </div>{/* end scrollable middle section */}

      {/* Library View — now rendered as full-page in main content area, removed from sidebar */}

      {/* WORKSPACES SECTION
      <div style={{ flexShrink: 0, marginTop: "8px", marginBottom: "8px" }}>
        <div style={{
          padding: "0 16px 8px",
          fontSize: "11px",
          fontWeight: "600",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: isDark ? "#6b7280" : "#9ca3af",
        }}>
          Workspaces
        </div>
        <div style={{ padding: "4px 8px" }}>
          {workspaces.map((workspace) => {
            const Icon = workspace.icon;
            const isActive = activeWorkspace === workspace.id;
            return (
              <button
                key={workspace.id}
                onClick={() => {
                  setActiveWorkspace(workspace.id);
                  // Handle workspace selection
                  console.log(`Selected workspace: ${workspace.id}`);
                }}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  padding: "10px 12px",
                  borderRadius: "10px",
                  fontSize: "13px",
                  fontWeight: "500",
                  backgroundColor: isActive
                    ? isDark 
                      ? "rgba(59, 130, 246, 0.15)" 
                      : "rgba(59, 130, 246, 0.1)"
                    : "transparent",
                  color: isActive
                    ? isDark ? "#3B82F6" : "#2563EB"
                    : isDark ? "#d1d5db" : "#374151",
                  border: "none",
                  cursor: "pointer",
                  transition: "all 0.15s",
                  textAlign: "left",
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.backgroundColor = isDark 
                      ? "rgba(42, 42, 42, 0.5)" 
                      : "rgba(243, 244, 246, 0.8)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.backgroundColor = "transparent";
                  }
                }}
              >
                <Icon size={16} style={{ flexShrink: 0 }} />
                <span>{workspace.label}</span>
              </button>
            );
          })}
      </div>
      </div> */}

      {/* BETA DISCLAIMER */}
      <div style={{ flexShrink: 0, marginTop: "auto", padding: "16px" }}>
        <div style={{
          padding: "12px",
          borderRadius: "12px",
          backgroundColor: isDark ? "rgba(249, 115, 22, 0.05)" : "rgba(249, 115, 22, 0.1)",
          border: isDark ? "1px solid rgba(249, 115, 22, 0.2)" : "1px solid rgba(249, 115, 22, 0.3)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "6px" }}>
            <AlertTriangle size={14} color="#f97316" />
            <span style={{ fontSize: "11px", fontWeight: "700", color: "#f97316", letterSpacing: "0.05em" }}>BETA VERSION</span>
          </div>
          <p style={{
            fontSize: "10px",
            lineHeight: "1.5",
            color: isDark ? "#9ca3af" : "#4b5563",
            margin: 0
          }}>
            DigiRett is currently in beta. Responses may be incomplete or inaccurate and should not be treated as formal legal advice.
          </p>
        </div>
      </div>

      {/* UPGRADE TO PREMIUM CARD */}
      {/* <div style={{ flexShrink: 0 }}>
        <UpgradeCard theme={theme} />
      </div> */}
    </aside>
  );
};

export default Sidebar;
