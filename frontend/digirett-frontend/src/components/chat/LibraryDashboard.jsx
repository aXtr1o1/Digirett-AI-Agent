// frontend/digirett-frontend/src/components/chat/LibraryDashboard.jsx
import React, { useState, useEffect } from "react";
import {
  BookOpen,
  Search,
  Bookmark,
  Trash2,
  Calendar,
  Edit3,
  X,
  Check,
  StickyNote,
  Scale,
  Sparkles,
  ArrowRight,
  MessageCircle,
  AlertTriangle,
} from "lucide-react";
import libraryService from "../../services/libraryService";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const LibraryDashboard = ({ theme = "dark", onNavigateToConversation }) => {
  const isDark = theme === "dark";
  const [savedMessages, setSavedMessages] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [editingNoteId, setEditingNoteId] = useState(null);
  const [editNoteText, setEditNoteText] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);
  const [deleteThreadConfirmId, setDeleteThreadConfirmId] = useState(null);

  const loadSaved = async () => {
    const messages = await libraryService.getSavedMessages();
    setSavedMessages(messages);
  };

  useEffect(() => {
    loadSaved();
    window.addEventListener("digirett_library_updated", loadSaved);
    return () => window.removeEventListener("digirett_library_updated", loadSaved);
  }, []);

  const handleRemove = async (e, messageId) => {
    e.stopPropagation();
    try {
      await libraryService.unsaveMessage(messageId);
      setDeleteConfirmId(null);
      setExpandedId(null);
      loadSaved();
    } catch (err) {
      console.error("Failed to remove saved message:", err);
    }
  };

  const handleRemoveThread = async (e, conv) => {
    e.stopPropagation();
    try {
      // Unsave all messages in this conversation in parallel
      await Promise.all(conv.messages.map((msg) => libraryService.unsaveMessage(msg.message_id)));
      setDeleteThreadConfirmId(null);
      loadSaved();
    } catch (err) {
      console.error("Failed to remove saved conversation thread:", err);
    }
  };

  const handleNavigate = (conversationId) => {
    if (onNavigateToConversation) {
      onNavigateToConversation(conversationId);
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

  // Group saved messages by conversation_id to show them as unified threads
  const groupMessagesByConversation = (messagesList) => {
    const grouped = [];
    const convMap = {};

    messagesList.forEach((msg) => {
      const convId = msg.conversation_id || "unknown";
      if (!convMap[convId]) {
        convMap[convId] = {
          conversation_id: convId,
          conversation_title: msg.conversation_title || "Untitled Conversation",
          messages: [],
          latest_saved_at: msg.saved_at,
        };
        grouped.push(convMap[convId]);
      }
      convMap[convId].messages.push(msg);
      if (new Date(msg.saved_at) > new Date(convMap[convId].latest_saved_at)) {
        convMap[convId].latest_saved_at = msg.saved_at;
      }
    });

    // Sort conversations by latest_saved_at descending
    grouped.sort((a, b) => new Date(b.latest_saved_at) - new Date(a.latest_saved_at));

    // Sort messages inside each conversation chronologically
    grouped.forEach((conv) => {
      conv.messages.sort((a, b) => new Date(a.saved_at) - new Date(b.saved_at));
    });

    return grouped;
  };

  const filteredMessages = savedMessages.filter((msg) => {
    const q = searchQuery.toLowerCase();
    return (
      msg.content?.toLowerCase().includes(q) ||
      msg.conversation_title?.toLowerCase().includes(q) ||
      msg.note?.toLowerCase().includes(q)
    );
  });

  const groupedConversations = groupMessagesByConversation(filteredMessages);

  const formatDate = (isoString) => {
    if (!isoString) return "";
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return "";
    }
  };

  const textPrimary = isDark ? "#f1f5f9" : "#0f172a";
  const textSecondary = isDark ? "#94a3b8" : "#64748b";
  const textMuted = isDark ? "#4b5563" : "#9ca3af";
  const accentBlue = "#3b82f6";
  const cardBg = isDark ? "rgba(22, 22, 30, 0.85)" : "rgba(255, 255, 255, 0.92)";
  const cardBorder = isDark ? "1px solid rgba(255, 255, 255, 0.07)" : "1px solid rgba(0, 0, 0, 0.07)";

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* ── Header ── */}
      <div
        style={{
          flexShrink: 0,
          padding: "32px 40px 24px",
          borderBottom: isDark
            ? "1px solid rgba(255,255,255,0.06)"
            : "1px solid rgba(0,0,0,0.06)",
          background: isDark
            ? "linear-gradient(135deg, rgba(22,22,35,0.7) 0%, rgba(15,15,25,0.5) 100%)"
            : "linear-gradient(135deg, rgba(255,255,255,0.8) 0%, rgba(241,245,249,0.6) 100%)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "14px", marginBottom: "6px" }}>
          <div
            style={{
              width: "44px",
              height: "44px",
              borderRadius: "13px",
              background: "linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 4px 14px rgba(59,130,246,0.4)",
              flexShrink: 0,
            }}
          >
            <BookOpen size={20} color="#fff" />
          </div>
          <div style={{ flex: 1 }}>
            <h1 style={{ margin: 0, fontSize: "22px", fontWeight: "700", color: textPrimary }}>
              Legal Library
            </h1>
            <p style={{ margin: 0, fontSize: "13px", color: textSecondary, marginTop: "2px" }}>
              Access and annotate bookmarked AI legal references
            </p>
          </div>

          {savedMessages.length > 0 && (
            <div
              style={{
                padding: "6px 14px",
                borderRadius: "20px",
                background: isDark ? "rgba(59,130,246,0.12)" : "rgba(59,130,246,0.08)",
                border: `1px solid ${isDark ? "rgba(59,130,246,0.25)" : "rgba(59,130,246,0.2)"}`,
                fontSize: "12px",
                fontWeight: "600",
                color: accentBlue,
                display: "flex",
                alignItems: "center",
                gap: "5px",
                flexShrink: 0,
              }}
            >
              <Bookmark size={12} fill={accentBlue} />
              {savedMessages.length} saved {savedMessages.length === 1 ? "reference" : "references"}
            </div>
          )}
        </div>

        {/* Search */}
        <div style={{ position: "relative", maxWidth: "480px", marginTop: "20px" }}>
          <Search
            size={16}
            style={{
              position: "absolute",
              left: "14px",
              top: "50%",
              transform: "translateY(-50%)",
              color: textMuted,
              pointerEvents: "none",
            }}
          />
          <input
            type="text"
            placeholder="Search saved legal references..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: "100%",
              padding: "10px 38px 10px 40px",
              borderRadius: "10px",
              fontSize: "13px",
              backgroundColor: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)",
              color: textPrimary,
              border: isDark ? "1px solid rgba(255,255,255,0.1)" : "1px solid rgba(0,0,0,0.1)",
              outline: "none",
              transition: "border-color 0.2s, box-shadow 0.2s",
              boxSizing: "border-box",
            }}
            onFocus={(e) => {
              e.target.style.borderColor = accentBlue;
              e.target.style.boxShadow = "0 0 0 3px rgba(59,130,246,0.12)";
            }}
            onBlur={(e) => {
              e.target.style.borderColor = isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)";
              e.target.style.boxShadow = "none";
            }}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              style={{
                position: "absolute",
                right: "12px",
                top: "50%",
                transform: "translateY(-50%)",
                background: "none",
                border: "none",
                cursor: "pointer",
                color: textMuted,
                padding: "2px",
                display: "flex",
              }}
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* 30-Day Retention Notice Banner */}
        <div
          style={{
            padding: "10px 14px",
            borderRadius: "10px",
            background: isDark ? "rgba(245, 158, 11, 0.08)" : "rgba(245, 158, 11, 0.05)",
            border: `1px solid ${isDark ? "rgba(245, 158, 11, 0.2)" : "rgba(245, 158, 11, 0.15)"}`,
            display: "flex",
            alignItems: "center",
            gap: "10px",
            fontSize: "12.5px",
            color: isDark ? "#fcd34d" : "#b45309",
            maxWidth: "760px",
            marginTop: "16px",
          }}
        >
          <AlertTriangle size={15} style={{ flexShrink: 0 }} />
          <span>
            <strong>Retention Notice:</strong> Saved references and conversations are retained in your library for <strong>30 days</strong> from the date of saving, after which they are automatically cleared.
          </span>
        </div>
      </div>

      {/* ── Content ── */}
      <div
        style={{ flex: 1, overflowY: "auto", padding: "28px 40px 40px" }}
        className="sidebar-scrollbar-hidden"
      >
        {/* Empty State */}
        {savedMessages.length === 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              minHeight: "400px",
              textAlign: "center",
            }}
          >
            <div
              style={{
                width: "80px",
                height: "80px",
                borderRadius: "20px",
                background: isDark ? "rgba(59,130,246,0.08)" : "rgba(59,130,246,0.06)",
                border: isDark ? "1px solid rgba(59,130,246,0.15)" : "1px solid rgba(59,130,246,0.12)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: "20px",
              }}
            >
              <Bookmark size={32} color={accentBlue} strokeWidth={1.5} />
            </div>
            <h2 style={{ margin: "0 0 8px", fontSize: "20px", fontWeight: "600", color: textPrimary }}>
              Your Library is empty
            </h2>
            <p style={{ margin: 0, fontSize: "14px", color: textSecondary, maxWidth: "360px", lineHeight: "1.6" }}>
              Bookmark important AI legal advice, rules, or responses in your chats to save them here for annotation.
            </p>
            <div
              style={{
                marginTop: "28px",
                padding: "14px 20px",
                borderRadius: "12px",
                background: isDark ? "rgba(59,130,246,0.06)" : "rgba(59,130,246,0.04)",
                border: isDark ? "1px solid rgba(59,130,246,0.12)" : "1px solid rgba(59,130,246,0.1)",
                fontSize: "13px",
                color: textSecondary,
                display: "flex",
                alignItems: "center",
                gap: "8px",
                maxWidth: "400px",
              }}
            >
              <Sparkles size={14} color={accentBlue} style={{ flexShrink: 0 }} />
              <span>
                Hover any AI response in chat → click{" "}
                <strong style={{ color: accentBlue }}>🔖 Save to Library</strong>
              </span>
            </div>
          </div>
        )}

        {/* No search results */}
        {savedMessages.length > 0 && filteredMessages.length === 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              minHeight: "300px",
              textAlign: "center",
            }}
          >
            <Search size={36} color={textMuted} strokeWidth={1.5} style={{ marginBottom: "16px" }} />
            <p style={{ margin: 0, fontSize: "15px", color: textSecondary }}>
              No results for <strong>"{searchQuery}"</strong>
            </p>
            <button
              onClick={() => setSearchQuery("")}
              style={{
                marginTop: "12px",
                padding: "8px 16px",
                borderRadius: "8px",
                border: "none",
                background: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.05)",
                color: textSecondary,
                fontSize: "12px",
              }}
            >
              Clear search
            </button>
          </div>
        )}

        {/* Grouped Conversations Thread List */}
        {groupedConversations.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "28px",
              maxWidth: "880px",
              margin: "0 auto",
            }}
          >
            {groupedConversations.map((conv) => {
              const isThreadDeleteConfirm = deleteThreadConfirmId === conv.conversation_id;

              return (
                <div
                  key={conv.conversation_id}
                  style={{
                    background: cardBg,
                    border: cardBorder,
                    borderRadius: "20px",
                    overflow: "hidden",
                    backdropFilter: "blur(20px)",
                    WebkitBackdropFilter: "blur(20px)",
                    boxShadow: isDark ? "0 4px 24px rgba(0,0,0,0.3)" : "0 4px 24px rgba(0,0,0,0.05)",
                    display: "flex",
                    flexDirection: "column",
                    transition: "transform 0.2s, box-shadow 0.2s",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = "translateY(-2px)";
                    e.currentTarget.style.boxShadow = isDark
                      ? "0 8px 36px rgba(0,0,0,0.4)"
                      : "0 8px 36px rgba(0,0,0,0.08)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = "translateY(0)";
                    e.currentTarget.style.boxShadow = isDark
                      ? "0 4px 24px rgba(0,0,0,0.3)"
                      : "0 4px 24px rgba(0,0,0,0.05)";
                  }}
                >
                  {/* Accent bar */}
                  <div style={{ height: "4px", background: "linear-gradient(90deg, #3b82f6 0%, #6366f1 100%)" }} />

                  {/* Card Header */}
                  <div
                    style={{
                      padding: "20px 24px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "16px",
                      borderBottom: isDark ? "1px solid rgba(255,255,255,0.05)" : "1px solid rgba(0,0,0,0.05)",
                      background: isDark ? "rgba(0, 0, 0, 0.1)" : "rgba(0, 0, 0, 0.01)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0, flex: 1 }}>
                      <div
                        style={{
                          width: "36px",
                          height: "36px",
                          borderRadius: "10px",
                          background: isDark ? "rgba(59,130,246,0.12)" : "rgba(59,130,246,0.06)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: accentBlue,
                          flexShrink: 0,
                        }}
                      >
                        <MessageCircle size={18} />
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <h3
                          style={{
                            margin: 0,
                            fontSize: "15px",
                            fontWeight: "600",
                            color: textPrimary,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {conv.conversation_title}
                        </h3>
                        <div style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "11px", color: textMuted, marginTop: "2px" }}>
                          <Calendar size={11} />
                          <span>{conv.messages.length} saved {conv.messages.length === 1 ? "message" : "messages"}</span>
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", flexShrink: 0 }}>
                      <button
                        onClick={() => handleNavigate(conv.conversation_id)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                          background: "none",
                          border: isDark ? "1px solid rgba(255,255,255,0.1)" : "1px solid rgba(0,0,0,0.1)",
                          borderRadius: "8px",
                          padding: "6px 12px",
                          cursor: "pointer",
                          fontSize: "12px",
                          fontWeight: "500",
                          color: textSecondary,
                          transition: "all 0.2s",
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.borderColor = accentBlue;
                          e.currentTarget.style.color = accentBlue;
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.borderColor = isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)";
                          e.currentTarget.style.color = textSecondary;
                        }}
                      >
                        <span>Go to Chat</span>
                        <ArrowRight size={12} />
                      </button>

                      {isThreadDeleteConfirm ? (
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <button
                            onClick={(e) => { e.stopPropagation(); setDeleteThreadConfirmId(null); }}
                            style={{
                              padding: "6px 10px",
                              borderRadius: "8px",
                              fontSize: "12px",
                              border: isDark ? "1px solid rgba(255,255,255,0.1)" : "1px solid rgba(0,0,0,0.1)",
                              background: "transparent",
                              color: textSecondary,
                              cursor: "pointer",
                            }}
                          >
                            Cancel
                          </button>
                          <button
                            onClick={(e) => handleRemoveThread(e, conv)}
                            style={{
                              padding: "6px 10px",
                              borderRadius: "8px",
                              fontSize: "12px",
                              border: "none",
                              background: "rgba(239,68,68,0.12)",
                              color: "#ef4444",
                              cursor: "pointer",
                              fontWeight: "600",
                            }}
                          >
                            Remove Thread
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={(e) => { e.stopPropagation(); setDeleteThreadConfirmId(conv.conversation_id); }}
                          style={{
                            background: "none",
                            border: "none",
                            cursor: "pointer",
                            padding: "8px",
                            borderRadius: "8px",
                            color: textMuted,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            transition: "all 0.2s",
                          }}
                          title="Remove conversation thread from library"
                          onMouseEnter={(e) => {
                            e.currentTarget.style.color = "#ef4444";
                            e.currentTarget.style.background = "rgba(239,68,68,0.08)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = textMuted;
                            e.currentTarget.style.background = "transparent";
                          }}
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Thread messages container */}
                  <div style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "20px" }}>
                    {conv.messages.map((msg) => {
                      const isUserMsg = msg.role === "user";
                      const isExpanded = expandedId === msg.message_id;
                      const isEditingNote = editingNoteId === msg.message_id;
                      const isDeleteConfirm = deleteConfirmId === msg.message_id;

                      if (isUserMsg) {
                        return (
                          <div
                            key={msg.message_id}
                            style={{
                              display: "flex",
                              flexDirection: "column",
                              alignItems: "flex-end",
                              width: "100%",
                            }}
                          >
                            <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px", paddingRight: "8px" }}>
                              <span style={{ fontSize: "11px", fontWeight: "600", color: textSecondary }}>User Question</span>
                            </div>
                            <div
                              style={{
                                maxWidth: "85%",
                                background: isDark ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.02)",
                                border: isDark ? "1px solid rgba(255, 255, 255, 0.05)" : "1px solid rgba(0, 0, 0, 0.04)",
                                borderRadius: "16px 16px 4px 16px",
                                padding: "12px 16px",
                                fontSize: "13px",
                                color: textPrimary,
                                lineHeight: "1.6",
                                wordBreak: "break-word",
                              }}
                            >
                              {msg.content}
                            </div>
                          </div>
                        );
                      }

                      return (
                        <div
                          key={msg.message_id}
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "flex-start",
                            width: "100%",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px", paddingLeft: "8px" }}>
                            <Scale size={11} color={accentBlue} />
                            <span style={{ fontSize: "11px", fontWeight: "600", color: accentBlue }}>AI Response</span>
                          </div>
                          <div
                            style={{
                              width: "100%",
                              background: isDark ? "rgba(59, 130, 246, 0.03)" : "rgba(59, 130, 246, 0.01)",
                              border: isDark ? "1px solid rgba(59, 130, 246, 0.1)" : "1px solid rgba(59, 130, 246, 0.08)",
                              borderRadius: "16px 16px 16px 4px",
                              padding: "18px 20px",
                              position: "relative",
                            }}
                          >
                            {/* Message content */}
                            <div
                              style={{
                                fontSize: "13.5px",
                                lineHeight: "1.7",
                                color: isDark ? "#cbd5e1" : "#374151",
                                ...(isExpanded
                                  ? {}
                                  : {
                                      display: "-webkit-box",
                                      WebkitLineClamp: 6,
                                      WebkitBoxOrient: "vertical",
                                      overflow: "hidden",
                                      textOverflow: "ellipsis",
                                      maxHeight: "135px",
                                    }),
                              }}
                            >
                              {isExpanded ? (
                                <ReactMarkdown
                                  remarkPlugins={[remarkGfm]}
                                  components={{
                                    p: (props) => <p style={{ marginBottom: "12px" }} {...props} />,
                                    ul: (props) => <ul style={{ paddingLeft: "20px", marginBottom: "12px", listStyleType: "disc" }} {...props} />,
                                    ol: (props) => <ol style={{ paddingLeft: "20px", marginBottom: "12px", listStyleType: "decimal" }} {...props} />,
                                    li: (props) => <li style={{ marginBottom: "4px" }} {...props} />,
                                    strong: (props) => <strong style={{ fontWeight: "600", color: textPrimary }} {...props} />,
                                    h2: (props) => <h2 style={{ fontSize: "15px", fontWeight: "700", margin: "14px 0 8px", color: textPrimary }} {...props} />,
                                    h3: (props) => <h3 style={{ fontSize: "14px", fontWeight: "600", margin: "12px 0 6px", color: textPrimary }} {...props} />,
                                  }}
                                >
                                  {msg.content}
                                </ReactMarkdown>
                              ) : (
                                msg.content
                              )}
                            </div>

                            {msg.content && msg.content.length > 350 && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setExpandedId(isExpanded ? null : msg.message_id);
                                }}
                                style={{
                                  background: "none",
                                  border: "none",
                                  padding: "6px 0",
                                  fontSize: "11px",
                                  color: accentBlue,
                                  cursor: "pointer",
                                  marginTop: "8px",
                                  fontWeight: "600",
                                }}
                              >
                                {isExpanded ? "Show less ↑" : "Read full response ↓"}
                              </button>
                            )}

                            {/* Citations/Sources */}
                            {msg.sources && msg.sources.length > 0 && (
                              <div style={{ marginTop: "14px", borderTop: isDark ? "1px solid rgba(255,255,255,0.05)" : "1px solid rgba(0,0,0,0.05)", paddingTop: "10px" }}>
                                <span style={{ fontSize: "11px", fontWeight: "600", color: textSecondary, display: "block", marginBottom: "4px" }}>
                                  Sources & Citations:
                                </span>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                                  {msg.sources.map((src, idx) => (
                                    <a
                                      key={idx}
                                      href={src.url || "#"}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      style={{
                                        fontSize: "10.5px",
                                        color: accentBlue,
                                        textDecoration: "none",
                                        background: isDark ? "rgba(59, 130, 246, 0.08)" : "rgba(59, 130, 246, 0.04)",
                                        padding: "3px 8px",
                                        borderRadius: "4px",
                                        border: `1px solid ${isDark ? "rgba(59, 130, 246, 0.15)" : "rgba(59, 130, 246, 0.1)"}`,
                                      }}
                                    >
                                      {src.title || src.name || `Source ${idx + 1}`}
                                    </a>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Note Section & Single Message Delete */}
                            <div
                              style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "flex-start",
                                marginTop: "14px",
                                borderTop: isDark ? "1px solid rgba(255,255,255,0.05)" : "1px solid rgba(0,0,0,0.05)",
                                paddingTop: "12px",
                                gap: "16px",
                              }}
                            >
                              <div style={{ flex: 1 }}>
                                {isEditingNote ? (
                                  <div onClick={(e) => e.stopPropagation()}>
                                    <textarea
                                      value={editNoteText}
                                      onChange={(e) => setEditNoteText(e.target.value)}
                                      placeholder="Write your personal annotation note..."
                                      rows={2}
                                      style={{
                                        width: "100%",
                                        fontSize: "12px",
                                        padding: "8px",
                                        borderRadius: "8px",
                                        backgroundColor: isDark ? "rgba(0,0,0,0.3)" : "#fff",
                                        color: textPrimary,
                                        border: isDark ? "1px solid rgba(255,255,255,0.15)" : "1px solid rgba(0,0,0,0.12)",
                                        outline: "none",
                                        resize: "none",
                                        boxSizing: "border-box",
                                      }}
                                    />
                                    <div style={{ display: "flex", gap: "6px", justifyContent: "flex-end", marginTop: "6px" }}>
                                      <button
                                        onClick={cancelEditing}
                                        style={{
                                          padding: "3px 8px",
                                          borderRadius: "4px",
                                          fontSize: "11px",
                                          border: isDark ? "1px solid rgba(255,255,255,0.1)" : "1px solid rgba(0,0,0,0.1)",
                                          background: "transparent",
                                          color: textSecondary,
                                          cursor: "pointer",
                                        }}
                                      >
                                        Cancel
                                      </button>
                                      <button
                                        onClick={(e) => saveNote(e, msg.message_id)}
                                        style={{
                                          padding: "3px 8px",
                                          borderRadius: "4px",
                                          fontSize: "11px",
                                          border: "none",
                                          background: "#f59e0b",
                                          color: "#000",
                                          fontWeight: "600",
                                          cursor: "pointer",
                                        }}
                                      >
                                        Save Note
                                      </button>
                                    </div>
                                  </div>
                                ) : msg.note ? (
                                  <div
                                    style={{
                                      display: "flex",
                                      alignItems: "flex-start",
                                      gap: "8px",
                                      background: isDark ? "rgba(245,158,11,0.06)" : "rgba(245,158,11,0.03)",
                                      padding: "8px 12px",
                                      borderRadius: "8px",
                                      borderLeft: "3px solid #f59e0b",
                                    }}
                                  >
                                    <StickyNote size={12} color="#f59e0b" style={{ flexShrink: 0, marginTop: "2px" }} />
                                    <div style={{ flex: 1 }}>
                                      <p style={{ margin: 0, fontSize: "12px", color: isDark ? "#fcd34d" : "#92400e", lineHeight: "1.5" }}>
                                        {msg.note}
                                      </p>
                                    </div>
                                    <button
                                      onClick={(e) => startEditingNote(e, msg)}
                                      style={{ background: "none", border: "none", cursor: "pointer", padding: "2px", color: "#f59e0b", display: "flex" }}
                                    >
                                      <Edit3 size={12} />
                                    </button>
                                  </div>
                                ) : (
                                  <button
                                    onClick={(e) => startEditingNote(e, msg)}
                                    style={{
                                      display: "inline-flex",
                                      alignItems: "center",
                                      gap: "4px",
                                      background: "none",
                                      border: "none",
                                      padding: "4px 8px",
                                      cursor: "pointer",
                                      fontSize: "11.5px",
                                      color: textMuted,
                                      borderRadius: "6px",
                                    }}
                                    onMouseEnter={(e) => { e.currentTarget.style.color = "#f59e0b"; }}
                                    onMouseLeave={(e) => { e.currentTarget.style.color = textMuted; }}
                                  >
                                    <StickyNote size={12} />
                                    <span>Add annotation note</span>
                                  </button>
                                )}
                              </div>

                              {/* Single Message Delete button */}
                              <div style={{ flexShrink: 0 }}>
                                {isDeleteConfirm ? (
                                  <div style={{ display: "flex", gap: "4px" }}>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); setDeleteConfirmId(null); }}
                                      style={{ padding: "4px 8px", borderRadius: "6px", fontSize: "10px", border: isDark ? "1px solid rgba(255,255,255,0.1)" : "1px solid rgba(0,0,0,0.1)", background: "transparent", color: textSecondary, cursor: "pointer" }}
                                    >
                                      Cancel
                                    </button>
                                    <button
                                      onClick={(e) => handleRemove(e, msg.message_id)}
                                      style={{ padding: "4px 8px", borderRadius: "6px", fontSize: "10px", border: "none", background: "rgba(239,68,68,0.12)", color: "#ef4444", cursor: "pointer", fontWeight: "600" }}
                                    >
                                      Remove
                                    </button>
                                  </div>
                                ) : (
                                  <button
                                    onClick={(e) => { e.stopPropagation(); setDeleteConfirmId(msg.message_id); }}
                                    style={{
                                      background: "none",
                                      border: "none",
                                      cursor: "pointer",
                                      padding: "6px",
                                      borderRadius: "6px",
                                      color: textMuted,
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "center",
                                    }}
                                    title="Remove this response from library"
                                    onMouseEnter={(e) => { e.currentTarget.style.color = "#ef4444"; e.currentTarget.style.background = "rgba(239,68,68,0.05)"; }}
                                    onMouseLeave={(e) => { e.currentTarget.style.color = textMuted; e.currentTarget.style.background = "transparent"; }}
                                  >
                                    <Trash2 size={13} />
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default LibraryDashboard;

