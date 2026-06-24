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
  AlertTriangle
} from "lucide-react";
import { useUser, useClerk } from "@clerk/clerk-react";
import { useNavigate } from "react-router-dom";
import hitlService from "../../services/hitlService";
import conversationService from "../../services/conversationService";
import UpgradeCard from "../common/UpgradeCard";
import QuotaPanel from "../chat/QuotaPanel";

const Sidebar = ({
  conversations,
  currentConversationId,
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

  const { user } = useUser();
  const { signOut } = useClerk();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await signOut();
    navigate("/sign-in");
  };

  const displayName = user?.username || user?.primaryEmailAddress?.emailAddress || "User";

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    };

    if (menuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [menuOpen]);

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
    { id: "library", label: "Library", icon: Menu },
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
    if (feature.path) {
      navigate(feature.path);
    }
  };

  const workspaces = [
    { id: "new-project", label: "New Project", icon: FolderPlus },
    { id: "image", label: "Image", icon: ImageIcon },
    { id: "presentation", label: "Presentation", icon: FileText },
    { id: "research", label: "Research", icon: Search },
  ];

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

        {/* CHAT HISTORY (when Chat feature is active) */}
        {activeFeature === "chat" && (
          <div
            style={{
              padding: "4px 8px",
            }}>
            {conversations.length === 0 ? (
              <div style={{
                padding: "16px 12px",
                textAlign: "center",
                fontSize: "12px",
                color: isDark ? "#6b7280" : "#9ca3af",
              }}>
                No conversations yet
              </div>
            ) : (
              conversations.map((c) => (
                <div
                  key={c.conversation_id}
                  onClick={() => onSelectConversation(c.conversation_id)}
                  style={{
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
                    const trash = e.currentTarget.querySelector(".trash-icon");
                    if (trash) trash.style.opacity = "1";
                  }}
                  onMouseLeave={(e) => {
                    if (c.conversation_id !== currentConversationId) {
                      e.currentTarget.style.backgroundColor = "transparent";
                    }
                    const trash = e.currentTarget.querySelector(".trash-icon");
                    if (trash) trash.style.opacity = "0";
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

                  <Trash2
                    size={13}
                    className="trash-icon"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteConversation(c.conversation_id);
                    }}
                    style={{
                      flexShrink: 0,
                      opacity: 0,
                      cursor: "pointer",
                      color: isDark ? "#6b7280" : "#9ca3af",
                      transition: "opacity 0.15s, color 0.15s",
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.color = "#ef4444"}
                    onMouseLeave={(e) => e.currentTarget.style.color = isDark ? "#6b7280" : "#9ca3af"}
                  />
                </div>
              ))
            )}
          </div>
        )}

      </div>{/* end scrollable middle section */}

      {/* YET TO BE IMPLEMENTED MESSAGE (for Archived and Library) */}
      {(activeFeature === "archived" || activeFeature === "library") && (
        <div style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "32px 16px",
        }}>
          <div style={{
            textAlign: "center",
            padding: "24px",
            borderRadius: "12px",
            backgroundColor: isDark
              ? "rgba(26, 26, 26, 0.6)"
              : "rgba(255, 255, 255, 0.6)",
            border: isDark
              ? "1px solid rgba(42, 42, 42, 0.5)"
              : "1px solid rgba(229, 231, 235, 0.5)",
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
          }}>
            <div style={{
              fontSize: "14px",
              fontWeight: "500",
              color: isDark ? "#d1d5db" : "#374151",
              marginBottom: "8px",
            }}>
              {activeFeature === "archived" ? "Archived" : "Library"}
            </div>
            <div style={{
              fontSize: "12px",
              color: isDark ? "#9ca3af" : "#6b7280",
            }}>
              Yet to be implemented
            </div>
          </div>
        </div>
      )}

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
