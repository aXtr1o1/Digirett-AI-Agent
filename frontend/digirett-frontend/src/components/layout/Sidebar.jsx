import { Trash2, MessageSquare } from "lucide-react";

const Sidebar = ({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  theme = "dark",
}) => {
  const isDark = theme === "dark";

  return (
    <aside
      style={{
        width: "260px",
        minWidth: "260px",
        maxWidth: "260px",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: isDark ? "#171717" : "#ececec",
        borderRight: isDark ? "1px solid #2a2a2a" : "1px solid #d1d5db",
        overflow: "hidden",
      }}
    >
      {/* APP TITLE */}
      <div style={{
        padding: "20px 16px 12px",
        fontSize: "15px",
        fontWeight: "600",
        color: isDark ? "#ffffff" : "#111827",
        flexShrink: 0,
      }}>
        DigiRett AI Assistant
      </div>

      {/* NEW CHAT BUTTON */}
      <div style={{ padding: "0 12px 12px", flexShrink: 0 }}>
        <button
        onClick={onNewChat}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "10px 14px",
          borderRadius: "12px",
          fontSize: "14px",
          fontWeight: "500",
          backgroundColor: isDark ? "#2f2f2f" : "#2563eb",   // ✅ FIXED
          color: isDark ? "#f3f4f6" : "#ffffff",              // ✅ FIXED
          border: isDark ? "1px solid #3f3f3f" : "none",      // ✅ Optional clean border
          cursor: "pointer",
          transition: "all 0.2s",
        }}
        onMouseEnter={e => {
          e.currentTarget.style.backgroundColor =
            isDark ? "#3a3a3a" : "#1d4ed8";
        }}
        onMouseLeave={e => {
          e.currentTarget.style.backgroundColor =
            isDark ? "#2f2f2f" : "#2563eb";
        }}
      >
        <span style={{ fontSize: "18px", lineHeight: 1, fontWeight: "700" }}>+</span>
        New Chat
      </button>
      </div>

      {/* HISTORY LABEL */}
      <div style={{
        padding: "0 16px 6px",
        fontSize: "11px",
        fontWeight: "600",
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        color: isDark ? "#6b7280" : "#9ca3af",
        flexShrink: 0,
      }}>
        Chat History
      </div>

      {/* SCROLLABLE LIST — forced scrollbar always visible */}
      <div
        style={{
          flex: 1,
          overflowY: "scroll",      /* scroll (not auto) forces scrollbar always visible */
          overflowX: "hidden",
          padding: "4px 8px",
          minHeight: 0,
        }}
      >
        {conversations.length === 0 && (
          <p style={{
            fontSize: "12px",
            color: isDark ? "#4b5563" : "#9ca3af",
            padding: "8px 12px",
          }}>
            No conversations yet
          </p>
        )}

        {conversations.map((c) => (
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
                  ? isDark ? "#2f2f2f" : "#ffffff"
                  : "transparent",
              color: isDark ? "#d1d5db" : "#374151",
              transition: "background-color 0.15s",
            }}
            onMouseEnter={e => {
              if (c.conversation_id !== currentConversationId) {
                e.currentTarget.style.backgroundColor = isDark ? "#252525" : "#ffffff";
              }
              const trash = e.currentTarget.querySelector(".trash-icon");
              if (trash) trash.style.opacity = "1";
            }}
            onMouseLeave={e => {
              if (c.conversation_id !== currentConversationId) {
                e.currentTarget.style.backgroundColor = "transparent";
              }
              const trash = e.currentTarget.querySelector(".trash-icon");
              if (trash) trash.style.opacity = "0";
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
              <MessageSquare size={13} style={{ flexShrink: 0, color: isDark ? "#6b7280" : "#9ca3af" }} />
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
              onMouseEnter={e => e.currentTarget.style.color = "#ef4444"}
              onMouseLeave={e => e.currentTarget.style.color = isDark ? "#6b7280" : "#9ca3af"}
            />
          </div>
        ))}
      </div>
    </aside>
  );
};

export default Sidebar;
