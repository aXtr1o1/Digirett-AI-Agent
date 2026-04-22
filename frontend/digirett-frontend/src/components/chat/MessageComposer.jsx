import React, { useState, useRef, useEffect } from "react";
import { StopCircle, Paperclip, ArrowUp, X } from "lucide-react";

const MessageComposer = ({
  onSend,
  disabled,
  isStreaming,
  isProcessingDoc,
  onStop,
  theme = "dark",
}) => {
  const [message, setMessage] = useState("");
  const [file, setFile] = useState(null);

  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  const isDark = theme === "dark";
  // treat doc processing same as streaming — block all input
  const isBusy = isStreaming || isProcessingDoc;

  // Auto resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      const newHeight = Math.min(textareaRef.current.scrollHeight, 200);
      textareaRef.current.style.height = newHeight + "px";
      textareaRef.current.style.overflowY =
        textareaRef.current.scrollHeight > 200 ? "scroll" : "hidden";
    }
  }, [message]);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  // File select
  const handleFileSelect = (e) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  // Remove file
  const removeFile = () => {
    setFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Send message
  const sendMessage = () => {
    if (isBusy || disabled) return;
    if (!message.trim() && !file) return;

    onSend({
      text: message,
      file: file,
    });

    setMessage("");
    setFile(null);

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.overflowY = "hidden";
    }
  };

  // ✅ Enter key sends; Shift+Enter inserts newline
  const handleKeyDown = (e) => {
    if (isBusy) return;

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const canSend = !disabled && !isBusy && (!!message.trim() || !!file);

  const getPlaceholder = () => {
    if (isProcessingDoc) return "Analysing document…";
    if (isBusy) return "Please wait…";
    if (file) return "Add a question about the document";
    return "Ask Anything...";
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "6px",
      }}
    >
      {/* File Preview */}
      {file && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "6px 10px",
            borderRadius: "8px",
            backgroundColor: isDark
              ? "rgba(59, 130, 246, 0.1)"
              : "rgba(59, 130, 246, 0.08)",
            fontSize: "13px",
            color: isDark ? "#d1d5db" : "#374151",
          }}
        >
          <span>📄 {file.name}</span>
          <button
            onClick={removeFile}
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              color: "#ef4444",
            }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Processing hint shown above input */}
      {isProcessingDoc && (
        <div
          style={{
            fontSize: "12px",
            textAlign: "center",
            color: isDark ? "#6b7280" : "#9ca3af",
            padding: "2px 0",
          }}
        >
          Analysing document — please wait…
        </div>
      )}

      {/* Input Box */}
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
          opacity: isBusy ? 0.7 : 1,
          transition: "opacity 0.2s",
        }}
      >
        {/* Upload Button */}
        <button
          type="button"
          onClick={() => !isBusy && fileInputRef.current?.click()}
          style={{
            width: "36px",
            height: "36px",
            borderRadius: "50%",
            border: "none",
            cursor: isBusy ? "not-allowed" : "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "transparent",
            color: isDark ? "#9ca3af" : "#6b7280",
            flexShrink: 0,
            opacity: isBusy ? 0.4 : 1,
          }}
        >
          <Paperclip size={18} />
        </button>

        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileSelect}
          accept=".pdf,.docx,.doc"
          style={{ display: "none" }}
        />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isBusy || disabled}
          rows={1}
          placeholder={getPlaceholder()}
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
            cursor: isBusy ? "not-allowed" : "text",
          }}
        />

        {/* Send / Stop */}
        {isBusy ? (
          isStreaming ? (
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
              }}
            >
              <StopCircle size={18} />
            </button>
          ) : (
            /* Doc processing spinner */
            <div
              style={{
                width: "40px",
                height: "40px",
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                style={{ animation: "spin 1s linear infinite" }}
              >
                <circle
                  cx="12" cy="12" r="10"
                  stroke={isDark ? "#4b5563" : "#d1d5db"}
                  strokeWidth="3"
                />
                <path
                  d="M12 2a10 10 0 0 1 10 10"
                  stroke="#3B82F6"
                  strokeWidth="3"
                  strokeLinecap="round"
                />
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              </svg>
            </div>
          )
        ) : (
          <button
            type="button"
            onClick={sendMessage}
            disabled={!canSend}
            style={{
              width: "40px",
              height: "40px",
              borderRadius: "50%",
              backgroundColor: canSend
                ? "#3B82F6"
                : "rgba(59, 130, 246, 0.4)",
              border: "none",
              cursor: canSend ? "pointer" : "not-allowed",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#ffffff",
            }}
          >
            <ArrowUp size={18} />
          </button>
        )}
      </div>
    </div>
  );
};

export default MessageComposer;