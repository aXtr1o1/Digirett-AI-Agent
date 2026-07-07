import React, { useState, useEffect, useRef } from "react";
import { CheckCircle, X, Scale, Bell } from "lucide-react";

const SystemNotification = ({ notifications, onDismiss, onNavigate, isDark, currentView }) => {
  const [isOpen, setIsOpen] = useState(false); // Default to closed, requiring click to view
  const [isMobile, setIsMobile] = useState(window.innerWidth < 640);
  const [isMobileOrTablet, setIsMobileOrTablet] = useState(window.innerWidth < 1024);
  const containerRef = useRef(null);

  // Close the dropdown when the view changes
  useEffect(() => {
    setIsOpen(false);
  }, [currentView]);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 640);
      setIsMobileOrTablet(window.innerWidth < 1024);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Close the dropdown when clicking outside of the notification area
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("touchstart", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
    };
  }, [isOpen]);

  // Dragging interaction state
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const isDraggingRef = useRef(false);
  const totalDragDistanceRef = useRef(0);

  const handleDragStart = (clientX, clientY) => {
    dragStartRef.current = { x: clientX, y: clientY };
    isDraggingRef.current = true;
    setIsDragging(true);
    totalDragDistanceRef.current = 0;
  };

  const handleDragMove = (clientX, clientY) => {
    if (!isDraggingRef.current || !containerRef.current) return;
    const dx = clientX - dragStartRef.current.x;
    const dy = clientY - dragStartRef.current.y;

    const rect = containerRef.current.getBoundingClientRect();
    const newLeft = rect.left + dx;
    const newTop = rect.top + dy;

    // Clamp inside viewport borders with a 8px margin
    const clampedLeft = Math.max(8, Math.min(window.innerWidth - rect.width - 8, newLeft));
    const clampedTop = Math.max(8, Math.min(window.innerHeight - rect.height - 8, newTop));

    const dx_clamped = clampedLeft - rect.left;
    const dy_clamped = clampedTop - rect.top;

    setPosition((prev) => ({
      x: prev.x + dx_clamped,
      y: prev.y + dy_clamped,
    }));

    dragStartRef.current = { x: clientX, y: clientY };
    totalDragDistanceRef.current += Math.sqrt(dx_clamped * dx_clamped + dy_clamped * dy_clamped);
  };

  const handleDragEnd = () => {
    isDraggingRef.current = false;
    setIsDragging(false);
  };

  const onMouseDown = (e) => {
    if (!isMobileOrTablet) return;
    handleDragStart(e.clientX, e.clientY);

    const handleMouseMove = (event) => {
      handleDragMove(event.clientX, event.clientY);
    };

    const handleMouseUp = () => {
      handleDragEnd();
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  };

  const onTouchStart = (e) => {
    if (!isMobileOrTablet) return;
    const touch = e.touches[0];
    handleDragStart(touch.clientX, touch.clientY);
  };

  const onTouchMove = (e) => {
    if (!isMobileOrTablet) return;
    const touch = e.touches[0];
    handleDragMove(touch.clientX, touch.clientY);
  };

  const onTouchEnd = () => {
    handleDragEnd();
  };

  const handleToggleClick = (e) => {
    if (totalDragDistanceRef.current > 5) {
      return;
    }
    setIsOpen(!isOpen);
  };

  const [rightOffset, setRightOffset] = useState(32);

  useEffect(() => {
    const updatePosition = () => {
      const legalPanel = document.getElementById("legal-panel-aside");
      const isPanelOpen = legalPanel !== null;
      setRightOffset(isPanelOpen ? 320 + 32 : 32);
    };

    updatePosition();

    window.addEventListener("resize", updatePosition);
    window.addEventListener("transitionend", updatePosition);

    const interval = setInterval(updatePosition, 300);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("transitionend", updatePosition);
      clearInterval(interval);
    };
  }, [currentView, notifications]);

  if (!notifications || notifications.length === 0) return null;

  const count = notifications.length;

  return (
    <div
      ref={containerRef}
      style={{
        position: "fixed",
        bottom: (window.location.pathname === "/" || window.location.pathname.startsWith("/chat")) && currentView !== "library"
          ? "calc((var(--composer-height, 90px) - 56px) / 2 + 10px)"
          : (isMobile ? "16px" : "32px"),
        right: isMobile ? "16px" : `${rightOffset}px`,
        left: "auto",
        zIndex: 2147483647,
        display: "flex",
        flexDirection: "column",
        alignItems: isMobile ? "stretch" : "flex-end",
        gap: "16px",
        pointerEvents: "none",
        transform: `translate(${position.x}px, ${position.y}px)`,
      }}
    >
      {/* Notification Stack */}
      {isOpen && (
        <div
          style={{
            display: "flex",
            flexDirection: "column", // Stack from top to bottom
            gap: "12px",
            width: isMobile ? "calc(100vw - 32px)" : "420px",
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
        onClick={handleToggleClick}
        onMouseDown={onMouseDown}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        style={{
          pointerEvents: "auto",
          alignSelf: "flex-end",
          backgroundColor: "transparent",
          color: isDark ? "#ffffff" : "#374151",
          border: "none",
          borderRadius: "12px",
          width: "40px",
          height: "40px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: isMobileOrTablet ? (isDragging ? "grabbing" : "grab") : "pointer",
          position: "relative",
          transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
          transform: isOpen ? "scale(1)" : "scale(1.1)",
          touchAction: "none", // Prevent scrolling the page while dragging the button
        }}
        onMouseEnter={(e) => {
          if (!isDragging) {
            e.currentTarget.style.transform = "scale(1.1) translateY(-2px)";
            e.currentTarget.style.backgroundColor = isDark
              ? "rgba(42, 42, 42, 0.5)"
              : "rgba(243, 244, 246, 0.8)";
          }
        }}
        onMouseLeave={(e) => {
          if (!isDragging) {
            e.currentTarget.style.transform = isOpen ? "scale(1)" : "scale(1.1)";
            e.currentTarget.style.backgroundColor = "transparent";
          }
        }}
      >
        <Bell size={20} className={count > 0 ? "animate-bounce" : ""} />

        {count > 0 && (
          <div
            style={{
              position: "absolute",
              top: "-2px",
              right: "-2px",
              background: "#ef4444",
              color: "white",
              fontSize: "9px",
              fontWeight: "900",
              width: "18px",
              height: "18px",
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "none",
              boxShadow: "0 2px 4px rgba(0, 0, 0, 0.1)",
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
    onNavigate(notif.view || notif.conversation_id, notif);
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
          background: notif.type === 'new_message' ? '#3b82f6' : '#10b981',
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
              {isResolution ? "MATTER RESOLVED" : isNewCase ? "NEW MATTER" : notif.type === 'new_message' ? "NEW MESSAGE" : "LAWYER LINKED"}
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
