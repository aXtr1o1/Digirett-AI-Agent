// frontend/digirett-frontend/src/components/chat/LibraryPanel.jsx
import React, { useState, useEffect } from "react";
import { Search, Bookmark, Trash2, Calendar, Edit2, ExternalLink, Filter } from "lucide-react";
import libraryService from "../../services/libraryService";

const LibraryPanel = ({ isDark, onSelectConversation, setActiveFeature, filterConversationId, onClearFilter }) => {
  const [savedMessages, setSavedMessages] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [editingNoteId, setEditingNoteId] = useState(null);
  const [editNoteText, setEditNoteText] = useState("");

  const loadSaved = async () => {
    const messages = await libraryService.getSavedMessages();
    setSavedMessages(messages);
  };

  useEffect(() => {
    loadSaved();

    // Listen for updates from other components
    window.addEventListener("digirett_library_updated", loadSaved);
    return () => {
      window.removeEventListener("digirett_library_updated", loadSaved);
    };
  }, []);

  const handleRemove = async (e, messageId) => {
    e.stopPropagation();
    try {
      await libraryService.unsaveMessage(messageId);
      loadSaved();
    } catch (err) {
      console.error("Failed to remove saved message:", err);
    }
  };

  const handleNavigate = (conversationId) => {
    if (onSelectConversation) {
      onSelectConversation(conversationId);
    }
    if (setActiveFeature) {
      try {
        const archivedIdsStr = localStorage.getItem("digirett_archived_conversation_ids");
        const archivedIds = archivedIdsStr ? JSON.parse(archivedIdsStr) : [];
        if (Array.isArray(archivedIds) && archivedIds.includes(conversationId)) {
          setActiveFeature("archived");
        } else {
          setActiveFeature("chat");
        }
      } catch (err) {
        setActiveFeature("chat");
      }
    }
  };

  const startEditingNote = (e, msg) => {
    e.stopPropagation();
    setEditingNoteId(msg.message_id);
    setEditNoteText(msg.note || "");
  };

  const saveNote = async (e, messageId) => {
    e.stopPropagation();
    try {
      await libraryService.updateMessageNote(messageId, editNoteText);
      setEditingNoteId(null);
      setEditNoteText("");
      loadSaved();
    } catch (err) {
      console.error("Failed to save note:", err);
    }
  };

  const cancelEditing = (e) => {
    e.stopPropagation();
    setEditingNoteId(null);
    setEditNoteText("");
  };

  const filteredMessages = savedMessages.filter((msg) => {
    const matchesSearch = msg.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
      msg.conversation_title.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesConversation = filterConversationId ? msg.conversation_id === filterConversationId : true;
    return matchesSearch && matchesConversation;
  });

  const formatDate = (isoString) => {
    if (!isoString) return "";
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    } catch {
      return "";
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        width: "100%",
        padding: "0px 8px 8px",
      }}
    >
      {/* Title Header */}
      <div
        style={{
          padding: "0 8px 12px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          borderBottom: isDark ? "1px solid rgba(255, 255, 255, 0.05)" : "1px solid rgba(0, 0, 0, 0.05)",
          marginBottom: "12px",
        }}
      >
        <Bookmark size={18} className="text-blue-500" />
        <span style={{ fontSize: "14px", fontWeight: "600", color: isDark ? "#ffffff" : "#111827" }}>
          Legal Library ({savedMessages.length})
        </span>
      </div>

      {/* Conversation Filter Badge */}
      {filterConversationId && (
        <div
          style={{
            margin: "0 4px 12px",
            padding: "8px 10px",
            borderRadius: "8px",
            backgroundColor: isDark ? "rgba(59, 130, 246, 0.1)" : "rgba(59, 130, 246, 0.05)",
            border: isDark ? "1px solid rgba(59, 130, 246, 0.2)" : "1px solid rgba(59, 130, 246, 0.15)",
            fontSize: "11px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "6px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "4px", minWidth: 0, flex: 1 }}>
            <Filter size={10} style={{ color: isDark ? "#60a5fa" : "#2563eb", flexShrink: 0 }} />
            <span
              style={{
                color: isDark ? "#93c5fd" : "#1d4ed8",
                fontWeight: "500",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              Filtered by Chat
            </span>
          </div>
          <button
            onClick={onClearFilter}
            style={{
              border: "none",
              background: "none",
              color: isDark ? "#60a5fa" : "#2563eb",
              cursor: "pointer",
              fontSize: "11px",
              fontWeight: "600",
              padding: 0,
              flexShrink: 0,
            }}
          >
            Show All
          </button>
        </div>
      )}

      {/* Search Input */}
      {savedMessages.length > 0 && (
        <div style={{ padding: "0 4px 12px", position: "relative" }}>
          <Search
            size={14}
            style={{
              position: "absolute",
              left: "14px",
              top: "50%",
              transform: "translateY(-50%)",
              color: isDark ? "#6b7280" : "#9ca3af",
            }}
          />
          <input
            type="text"
            placeholder="Search saved answers..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 12px 8px 30px",
              borderRadius: "8px",
              fontSize: "12px",
              backgroundColor: isDark ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.03)",
              color: isDark ? "#ffffff" : "#111827",
              border: isDark ? "1px solid rgba(255, 255, 255, 0.1)" : "1px solid rgba(0, 0, 0, 0.1)",
              outline: "none",
              transition: "border-color 0.2s",
            }}
            onFocus={(e) => (e.target.style.borderColor = "#3b82f6")}
            onBlur={(e) => (e.target.style.borderColor = isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)")}
          />
        </div>
      )}

      {/* Saved items list */}
      <div
        className="sidebar-scrollbar-hidden"
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "8px",
          maxHeight: "calc(100vh - 280px)",
        }}
      >
        {filteredMessages.length === 0 ? (
          <div
            style={{
              padding: "24px 16px",
              textAlign: "center",
              fontSize: "12px",
              color: isDark ? "#6b7280" : "#9ca3af",
            }}
          >
            {savedMessages.length === 0 ? "Bookmark key messages or save entire conversations to see them here." : "No matching bookmarks found."}
          </div>
        ) : (
          filteredMessages.map((msg) => (
            <div
              key={msg.id}
              onClick={() => handleNavigate(msg.conversation_id)}
              style={{
                padding: "10px",
                borderRadius: "10px",
                backgroundColor: isDark ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.02)",
                border: isDark ? "1px solid rgba(255, 255, 255, 0.06)" : "1px solid rgba(0, 0, 0, 0.06)",
                cursor: "pointer",
                transition: "all 0.2s",
                display: "flex",
                flexDirection: "column",
                gap: "6px",
                position: "relative",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = isDark ? "rgba(255, 255, 255, 0.06)" : "rgba(0, 0, 0, 0.04)";
                e.currentTarget.style.transform = "translateY(-1px)";
                const actions = e.currentTarget.querySelector(".bookmark-actions");
                if (actions) actions.style.opacity = "1";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = isDark ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.02)";
                e.currentTarget.style.transform = "translateY(0)";
                const actions = e.currentTarget.querySelector(".bookmark-actions");
                if (actions) actions.style.opacity = "0";
              }}
            >
              {/* Header metadata */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px", minWidth: 0, flex: 1 }}>
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: "600",
                      color: "#3b82f6",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      maxWidth: "110px",
                    }}
                    title={msg.conversation_title}
                  >
                    {msg.conversation_title}
                  </span>
                  <span
                    style={{
                      fontSize: "9px",
                      fontWeight: "600",
                      padding: "1px 4px",
                      borderRadius: "4px",
                      backgroundColor: msg.role === "user"
                        ? (isDark ? "rgba(99, 102, 241, 0.15)" : "rgba(99, 102, 241, 0.1)")
                        : (isDark ? "rgba(59, 130, 246, 0.15)" : "rgba(59, 130, 246, 0.1)"),
                      color: msg.role === "user" ? "#818cf8" : "#60a5fa",
                      border: `1px solid ${msg.role === "user"
                        ? (isDark ? "rgba(99, 102, 241, 0.25)" : "rgba(99, 102, 241, 0.2)")
                        : (isDark ? "rgba(59, 130, 246, 0.25)" : "rgba(59, 130, 246, 0.2)")}`,
                      flexShrink: 0,
                    }}
                  >
                    {msg.role === "user" ? "Question" : "AI Answer"}
                  </span>
                </div>

                <div
                  className="bookmark-actions"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    opacity: 0,
                    transition: "opacity 0.15s",
                  }}
                >
                  <Trash2
                    size={12}
                    onClick={(e) => handleRemove(e, msg.message_id)}
                    style={{
                      color: isDark ? "#9ca3af" : "#6b7280",
                      cursor: "pointer",
                      transition: "color 0.15s",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = "#ef4444")}
                    onMouseLeave={(e) => (e.currentTarget.style.color = isDark ? "#9ca3af" : "#6b7280")}
                    title="Remove from library"
                  />
                  <ExternalLink
                    size={12}
                    style={{ color: isDark ? "#9ca3af" : "#6b7280" }}
                    title="Navigate to conversation"
                  />
                </div>
              </div>

              {/* Message Snippet */}
              <div
                style={{
                  fontSize: "12px",
                  lineHeight: "1.4",
                  color: isDark ? "#d1d5db" : "#374151",
                  display: "-webkit-box",
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "normal",
                  maxHeight: "50px",
                }}
              >
                {msg.content}
              </div>

              {/* Personal Annotations note block */}
              {editingNoteId === msg.message_id ? (
                <div
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    marginTop: "4px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "6px",
                  }}
                >
                  <textarea
                    value={editNoteText}
                    onChange={(e) => setEditNoteText(e.target.value)}
                    placeholder="Add personal note/annotation..."
                    rows={2}
                    style={{
                      width: "100%",
                      fontSize: "11px",
                      padding: "6px",
                      borderRadius: "6px",
                      backgroundColor: isDark ? "#1e1e1e" : "#ffffff",
                      color: isDark ? "#ffffff" : "#111827",
                      border: isDark ? "1px solid rgba(255, 255, 255, 0.15)" : "1px solid rgba(0, 0, 0, 0.15)",
                      outline: "none",
                      resize: "none",
                    }}
                  />
                  <div style={{ display: "flex", gap: "6px", justifyContent: "flex-end" }}>
                    <button
                      onClick={(e) => cancelEditing(e)}
                      style={{
                        padding: "2px 6px",
                        borderRadius: "4px",
                        fontSize: "10px",
                        border: isDark ? "1px solid rgba(255,255,255,0.1)" : "1px solid rgba(0,0,0,0.1)",
                        backgroundColor: "transparent",
                        color: isDark ? "#9ca3af" : "#4b5563",
                        cursor: "pointer",
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={(e) => saveNote(e, msg.message_id)}
                      style={{
                        padding: "2px 6px",
                        borderRadius: "4px",
                        fontSize: "10px",
                        border: "none",
                        backgroundColor: "#3b82f6",
                        color: "#ffffff",
                        cursor: "pointer",
                      }}
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : msg.note ? (
                <div
                  style={{
                    marginTop: "4px",
                    padding: "6px 8px",
                    borderRadius: "6px",
                    backgroundColor: isDark ? "rgba(245, 158, 11, 0.08)" : "rgba(245, 158, 11, 0.05)",
                    borderLeft: "2.5px solid #d97706",
                    fontSize: "11px",
                    color: isDark ? "#f59e0b" : "#b45309",
                    lineHeight: "1.4",
                    display: "flex",
                    flexDirection: "column",
                    gap: "2px",
                  }}
                >
                  <div>
                    <strong style={{ fontWeight: "600" }}>Note:</strong> {msg.note}
                  </div>
                  <button
                    onClick={(e) => startEditingNote(e, msg)}
                    style={{
                      border: "none",
                      background: "none",
                      fontSize: "10px",
                      color: isDark ? "#f59e0b" : "#b45309",
                      cursor: "pointer",
                      padding: 0,
                      alignSelf: "flex-end",
                      textDecoration: "underline",
                    }}
                  >
                    Edit note
                  </button>
                </div>
              ) : (
                <button
                  onClick={(e) => startEditingNote(e, msg)}
                  style={{
                    border: "none",
                    background: "none",
                    fontSize: "10px",
                    color: "#3b82f6",
                    cursor: "pointer",
                    padding: 0,
                    textAlign: "left",
                    alignSelf: "flex-start",
                    marginTop: "2px",
                  }}
                >
                  + Add annotation note
                </button>
              )}

              {/* Mapped sections & date */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  fontSize: "10px",
                  color: isDark ? "#6b7280" : "#9ca3af",
                  marginTop: "4px",
                  borderTop: isDark ? "1px solid rgba(255,255,255,0.05)" : "1px solid rgba(0,0,0,0.05)",
                  paddingTop: "4px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "3px" }}>
                  <Calendar size={10} />
                  <span>{formatDate(msg.saved_at)}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default LibraryPanel;
