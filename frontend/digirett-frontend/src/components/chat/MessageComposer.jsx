import React, { useState, useRef, useEffect } from "react";
import { Send, StopCircle, Paperclip, Settings, Grid3x3, Mic, ArrowUp, Star } from "lucide-react";

const MessageComposer = ({ onSend, disabled, isStreaming, onStop, theme = "dark" }) => {
  const [message, setMessage] = useState("");
  const textareaRef = useRef(null);
  const isDark = theme === "dark";

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      const newHeight = Math.min(textareaRef.current.scrollHeight, 200);
      textareaRef.current.style.height = newHeight + "px";
      // Show scrollbar only when content exceeds max height
      textareaRef.current.style.overflowY =
        textareaRef.current.scrollHeight > 200 ? "scroll" : "hidden";
    }
  }, [message]);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const sendMessage = () => {
    if (message.trim() && !disabled && !isStreaming) { 
      onSend(message);
      setMessage("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
        textareaRef.current.style.overflowY = "hidden";
      }
    }
  };

  const handleKeyDown = (e) => {
    if (isStreaming) return;

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "12px",
        borderRadius: "12px",
        padding: "14px 16px",
        border: isDark 
          ? "1px solid rgba(59, 130, 246, 0.2)" 
          : "1px solid rgba(59, 130, 246, 0.15)",
        backgroundColor: isDark 
          ? "rgba(30, 30, 30, 0.3)" 
          : "rgba(255, 255, 255, 0.5)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        boxShadow: isDark
          ? "0 0 10px rgba(59, 130, 246, 0.1), 0 0 20px rgba(37, 99, 235, 0.05)"
          : "0 0 10px rgba(96, 165, 250, 0.08), 0 0 20px rgba(147, 197, 253, 0.05)",
        transition: "all 0.2s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = isDark 
          ? "rgba(59, 130, 246, 0.3)" 
          : "rgba(59, 130, 246, 0.2)";
        e.currentTarget.style.boxShadow = isDark
          ? "0 0 15px rgba(59, 130, 246, 0.15), 0 0 30px rgba(37, 99, 235, 0.08)"
          : "0 0 15px rgba(96, 165, 250, 0.12), 0 0 30px rgba(147, 197, 253, 0.08)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = isDark 
          ? "rgba(59, 130, 246, 0.2)" 
          : "rgba(59, 130, 246, 0.15)";
        e.currentTarget.style.boxShadow = isDark
          ? "0 0 10px rgba(59, 130, 246, 0.1), 0 0 20px rgba(37, 99, 235, 0.05)"
          : "0 0 10px rgba(96, 165, 250, 0.08), 0 0 20px rgba(147, 197, 253, 0.05)";
      }}
    >
      <textarea
        ref={textareaRef}
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled || isStreaming}
        rows={1}
        placeholder="Ask Anything..."
        style={{
          flex: 1,
          resize: "none",
          background: "transparent",
          border: "none",
          outline: "none",
          fontSize: "16px",
          lineHeight: "24px",
          color: isDark ? "#f3f4f6" : "#111827",
          maxHeight: "200px",
          overflowY: "hidden",
          fontFamily: "inherit",
          padding: 0,
          minHeight: "24px",
          verticalAlign: "middle",
        }}
        className={isDark ? "placeholder-dark" : "placeholder-light"}
      />

      {/* Send Button */}
      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          style={{
            width: "40px",
            height: "40px",
            borderRadius: "50%",
            backgroundColor: "#ef4444",
            border: "none",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#ffffff",
            transition: "all 0.2s",
            flexShrink: 0,
          }}
          onMouseEnter={(e) => e.currentTarget.style.backgroundColor = "#dc2626"}
          onMouseLeave={(e) => e.currentTarget.style.backgroundColor = "#ef4444"}
        >
          <StopCircle size={18} />
        </button>
      ) : (
        <button
          type="button"
          onClick={sendMessage}
          disabled={disabled || !message.trim()}
          style={{
            width: "40px",
            height: "40px",
            borderRadius: "50%",
            backgroundColor: (!disabled && message.trim()) 
              ? (isDark ? "#3B82F6" : "#2563EB")
              : (isDark ? "rgba(59, 130, 246, 0.4)" : "rgba(37, 99, 235, 0.4)"),
            border: "none",
            cursor: (!disabled && message.trim()) ? "pointer" : "not-allowed",

            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#ffffff",
            transition: "all 0.2s",
            flexShrink: 0,
          }}
          onMouseEnter={(e) => {
            if (!disabled && message.trim()) {
              e.currentTarget.style.backgroundColor = isDark ? "#2563EB" : "#1D4ED8";
              e.currentTarget.style.transform = "scale(1.05)";
            }
          }}
          onMouseLeave={(e) => {
            if (!disabled && message.trim()) {
              e.currentTarget.style.backgroundColor = isDark ? "#3B82F6" : "#2563EB";
              e.currentTarget.style.transform = "scale(1)";
            }
          }}
        >
          <ArrowUp size={18} />
        </button>
      )}
    </div>
  );
};

export default MessageComposer;
