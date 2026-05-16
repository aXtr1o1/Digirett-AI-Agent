import React from "react";
import { CheckCircle, X, Scale } from "lucide-react";

const SystemNotification = ({ notifications, onDismiss, onNavigate, isDark }) => {
  if (!notifications || notifications.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        bottom: "24px",
        right: "32px",
        width: "450px",
        zIndex: 2147483647,
        display: "flex",
        flexDirection: "column-reverse", // Newest on bottom (near the bottom edge)
        gap: "12px",
        pointerEvents: "none", // Allow clicking through the container space
      }}
    >
      {notifications.map((notif, index) => (
        <NotificationItem
          key={notif.id}
          notif={notif}
          onDismiss={onDismiss}
          onNavigate={onNavigate}
          index={index}
        />
      ))}
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
        pointerEvents: "auto", // Re-enable clicks for the item itself
        width: "100%",
        cursor: "pointer",
        animation: isExiting ? "notifOut 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards" : "notifIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards",
        transition: "all 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
      }}
    >
      <div
        style={{
          background: "#10b981", // Consistent Green for all milestones
          borderRadius: "16px",
          padding: "16px 20px",
          boxShadow: "0 10px 30px rgba(0, 0, 0, 0.15)",
          display: "flex",
          alignItems: "center",
          gap: "16px",
          color: "white",
          position: "relative",
          border: "1px solid rgba(255, 255, 255, 0.1)",
        }}
      >
        {/* Left Icon - Hidden for professional lawyer notifications */}
        {!isNewCase && (
          <div style={{
            width: "40px",
            height: "40px",
            background: "rgba(255, 255, 255, 0.2)",
            borderRadius: "10px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0
          }}>
            {isResolution ? <CheckCircle size={22} /> : <Scale size={22} />}
          </div>
        )}

        {/* Text Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: "10px",
            fontWeight: "900",
            textTransform: "uppercase",
            letterSpacing: "1px",
            opacity: 0.9,
            marginBottom: "4px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center"
          }}>
            <span style={{
              background: "rgba(255, 255, 255, 0.25)",
              padding: "2px 6px",
              borderRadius: "4px",
              marginRight: "8px",
              textOverflow: "ellipsis",
              overflow: "hidden",
              whiteSpace: "nowrap",
              maxWidth: isNewCase ? "200px" : "80px"
            }}>
              {isNewCase ? notif.caseRef : `#${notif.caseRef}`}
            </span>
            <span style={{
              fontWeight: "900",
              color: "#ffffff"
            }}>
              {isResolution ? "CASE RESOLVED" : isNewCase ? "NEW CASE AVAILABLE" : "LAWYER LINKED"}
            </span>
          </div>
          <div style={{
            fontSize: "13px",
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

        {/* Close Button */}
        <button
          onClick={handleDismiss}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "white",
            padding: "4px",
            opacity: 0.8,
            flexShrink: 0
          }}
          onMouseEnter={(e) => e.currentTarget.style.opacity = "1"}
          onMouseLeave={(e) => e.currentTarget.style.opacity = "0.8"}
        >
          <X size={18} />
        </button>
      </div>

      <style>{`
        @keyframes notifIn {
          from { opacity: 0; transform: translateX(30px) translateY(10px); }
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

export default SystemNotification;
