import React, { useState, useRef, useEffect } from "react";
import { Send, StopCircle } from "lucide-react";

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
    if (message.trim() && !disabled) {
      onSend(message);
      setMessage("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
        textareaRef.current.style.overflowY = "hidden";
      }
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-end",
        gap: "12px",
        borderRadius: "16px",
        padding: "12px 14px",
        border: isDark ? "1px solid #3f3f3f" : "1px solid #d1d5db",
        backgroundColor: isDark ? "#2f2f2f" : "#ffffff",
        boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
      }}
    >
      <textarea
        ref={textareaRef}
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        placeholder="Type your message"
        style={{
          flex: 1,
          resize: "none",
          background: "transparent",
          border: "none",
          outline: "none",
          fontSize: "17px",
          lineHeight: "24px",
          color: isDark ? "#f3f4f6" : "#111827",
          maxHeight: "200px",
          overflowY: "hidden",   /* starts hidden, becomes scroll when long */
          fontFamily: "inherit",
        }}
        /* placeholder color via inline won't work directly, handled by CSS class */
        className={isDark ? "placeholder-dark" : "placeholder-light"}
      />

      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          style={{
            flexShrink: 0,
            height: "32px",
            width: "32px",
            borderRadius: "8px",
            backgroundColor: "#ef4444",
            border: "none",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#ffffff",
          }}
        >
          <StopCircle size={16} />
        </button>
      ) : (
        <button
          type="button"
          onClick={sendMessage}
          disabled={disabled || !message.trim()}
          style={{
            flexShrink: 0,
            height: "32px",
            width: "32px",
            borderRadius: "8px",
            backgroundColor: (!disabled && message.trim()) ? "#2563eb" : "#93c5fd",
            border: "none",
            cursor: (!disabled && message.trim()) ? "pointer" : "not-allowed",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#ffffff",
            transition: "background-color 0.2s",
          }}
          onMouseEnter={e => {
            if (!disabled && message.trim()) e.currentTarget.style.backgroundColor = "#1d4ed8";
          }}
          onMouseLeave={e => {
            if (!disabled && message.trim()) e.currentTarget.style.backgroundColor = "#2563eb";
          }}
        >
          <Send size={14} />
        </button>
      )}
    </div>
  );
};

export default MessageComposer;
