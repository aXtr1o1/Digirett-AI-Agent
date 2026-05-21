import React, { useState, useEffect } from "react";
import { CheckCircle, X, Scale, Bell } from "lucide-react";

const SystemNotification = ({ notifications, onDismiss, onNavigate, isDark, currentView }) => {
  const [isOpen, setIsOpen] = useState(false); // Default to closed, requiring click to view

  // Close the dropdown when the view changes
  useEffect(() => {
    setIsOpen(false);
  }, [currentView]);
  if (!notifications || notifications.length === 0) return null;

  const count = notifications.length;

  return (
    <div
      style={{
        position: "fixed",
        bottom: "32px",
        right: "32px",
        zIndex: 2147483647,
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-end",
        gap: "16px",
        pointerEvents: "none",
      }}
    >
      {/* Notification Stack */}
      {isOpen && (
        <div
          style={{
            display: "flex",
            flexDirection: "column", // Stack from top to bottom
            gap: "12px",
            width: "420px",
            pointerEvents: "none",
            maxHeight: "70vh",
            overflowY: "auto",
            padding: "8px",
            scrollbarWidth: "none",
            msOverflowStyle: "none",
          }}
        >
          {[...notifications].reverse().map((notif, index) => (
            <NotificationItem
              key={notif.id}
              notif={notif}
              onDismiss={onDismiss}
              onNavigate={onNavigate}
              index={index}
            />
          ))}
        </div>
      )}

      {/* Notification Toggle Badge */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          pointerEvents: "auto",
          background: isDark ? "#1e293b" : "#ffffff",
          color: isDark ? "#ffffff" : "#1e293b",
          border: `1px solid ${isDark ? "#334155" : "#e2e8f0"}`,
          borderRadius: "16px",
          width: "56px",
          height: "56px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
          cursor: "pointer",
          position: "relative",
          transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
          transform: isOpen ? "scale(1)" : "scale(1.1)",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.transform = "scale(1.1) translateY(-2px)")}
        onMouseLeave={(e) => (e.currentTarget.style.transform = isOpen ? "scale(1)" : "scale(1.1)")}
      >
        <Bell size={24} className={count > 0 ? "animate-bounce" : ""} />

        {count > 0 && (
          <div
            style={{
              position: "absolute",
              top: "-4px",
              right: "-4px",
              background: "#ef4444",
              color: "white",
              fontSize: "10px",
              fontWeight: "900",
              width: "22px",
              height: "22px",
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: `3px solid ${isDark ? "#1e293b" : "#ffffff"}`,
              boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
            }}
          >
            {count}
          </div>
        )}
      </button>

      <style>{`
        ::-webkit-scrollbar { display: none; }
        @keyframes notifIn {
          from { opacity: 0; transform: translateX(30px) translateY(20px); }
          to { opacity: 1; transform: translateX(0) translateY(0); }
        }
        @keyframes notifOut {
          from { opacity: 1; transform: translateX(0) scale(1); }
          to { opacity: 0; transform: translateX(30px) scale(0.9); }
        }
      `}</style>
    </div>
  );
};

const NotificationItem = ({ notif, onDismiss, onNavigate, index }) => {
  const [isExiting, setIsExiting] = React.useState(false);

  const handleDismiss = (e) => {
    if (e) e.stopPropagation();
    setIsExiting(true);
    setTimeout(() => {
      onDismiss(notif.id);
    }, 400);
  };

  const handleView = () => {
    if (notif.view) {
      onNavigate(notif.view);
    } else if (notif.conversation_id) {
      onNavigate(notif.conversation_id);
    }
    handleDismiss();
  };

  const isResolution = notif.type === 'resolved';
  const isNewCase = notif.type === 'new_case';

  return (
    <div
      onClick={handleView}
      style={{
        pointerEvents: "auto",
        width: "100%",
        cursor: "pointer",
        animation: isExiting ? "notifOut 0.4s forwards" : "notifIn 0.5s forwards",
        transition: "all 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
      }}
    >
      <div
        style={{
          background: "#10b981",
          borderRadius: "16px",
          padding: "14px 18px",
          boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
          display: "flex",
          alignItems: "center",
          gap: "14px",
          color: "white",
          position: "relative",
          border: "1px solid rgba(255, 255, 255, 0.1)",
        }}
      >
        {!isNewCase && (
          <div style={{
            width: "36px",
            height: "36px",
            background: "rgba(255, 255, 255, 0.2)",
            borderRadius: "10px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0
          }}>
            {isResolution ? <CheckCircle size={20} /> : <Scale size={20} />}
          </div>
        )}

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: "9px",
            fontWeight: "900",
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            opacity: 0.9,
            marginBottom: "3px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center"
          }}>
            <span style={{
              background: "rgba(255, 255, 255, 0.25)",
              padding: "1px 5px",
              borderRadius: "4px",
              marginRight: "6px",
              textOverflow: "ellipsis",
              overflow: "hidden",
              whiteSpace: "nowrap",
              maxWidth: isNewCase ? "200px" : "80px"
            }}>
              {isNewCase ? notif.caseRef : `#${notif.caseRef}`}
            </span>
            <span>
              {isResolution ? "MATTER RESOLVED" : isNewCase ? "NEW MATTER" : "LAWYER LINKED"}
            </span>
          </div>
          <div style={{
            fontSize: "12px",
            fontWeight: "700",
            lineHeight: "1.4",
            margin: 0,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden"
          }}>
            {notif.message}
          </div>
        </div>

        <button
          onClick={handleDismiss}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "white",
            padding: "4px",
            opacity: 0.6,
            flexShrink: 0
          }}
          onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
          onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.6")}
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
};

export default SystemNotification;
