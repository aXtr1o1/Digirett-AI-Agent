import React, { useState, useRef, useEffect } from "react";
import { StopCircle, Paperclip, ArrowUp, X, Scale, CheckCircle, Loader2 } from "lucide-react";

const MessageComposer = ({
  onSend,
  disabled,
  isStreaming,
  isProcessingDoc,
  onStop,
  onEscalate,
  isEscalated,
  showEscalate = true,
  theme = "dark",
}) => {
  const [message, setMessage] = useState("");
  const [file, setFile] = useState(null);
  const [showEscalateConfirm, setShowEscalateConfirm] = useState(false);
  const [isEscalating, setIsEscalating] = useState(false);
  const [showSuccessToast, setShowSuccessToast] = useState(false);

  const isBusy = disabled || isProcessingDoc || isStreaming;

  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  const isDark = theme === "dark";
  // treat doc processing same as streaming — block all input

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
          position: "relative",
        }}
      >
        {/* Success Toast */}
        {showSuccessToast && (
          <div style={{
            position: "absolute",
            top: "-60px",
            left: "50%",
            transform: "translateX(-50%)",
            padding: "10px 24px",
            borderRadius: "99px",
            boxShadow: "0 10px 30px rgba(0, 0, 0, 0.3)",
            backgroundColor: isDark ? "#1e293b" : "#ffffff",
            border: isDark ? "1px solid rgba(59, 130, 246, 0.2)" : "1px solid rgba(59, 130, 246, 0.1)",
            color: isDark ? "#60a5fa" : "#2563eb",
            display: "flex",
            alignItems: "center",
            gap: "10px",
            whiteSpace: "nowrap",
            zIndex: 100,
            animation: "toastIn 0.3s ease-out forwards",
          }}>
            <CheckCircle size={16} />
            <span style={{ fontSize: "14px", fontWeight: "600" }}>Request submitted successfully!</span>
            <style>{`
              @keyframes toastIn {
                from { opacity: 0; transform: translateX(-50%) translateY(10px); }
                to { opacity: 1; transform: translateX(-50%) translateY(0); }
              }
            `}</style>
          </div>
        )}

        {/* Lawyer Escalation Button (Only for Users) */}
        {showEscalate && (
          <div className="relative">
            {showEscalateConfirm && (
              <div style={{
                position: "absolute",
                bottom: "calc(100% + 12px)",
                right: "0",
                width: "256px",
                padding: "16px",
                borderRadius: "16px",
                boxShadow: "0 10px 30px rgba(0, 0, 0, 0.3)",
                backgroundColor: isDark ? "#1a1a1a" : "#ffffff",
                border: isDark ? "1px solid rgba(42, 42, 42, 0.5)" : "1px solid rgba(229, 231, 235, 0.5)",
                zIndex: 50,
              }}>
                {isEscalated ? (
                  <div style={{ textAlign: "center" }}>
                    <CheckCircle size={24} style={{ color: "#2563eb", marginBottom: "8px" }} />
                    <p style={{ fontSize: "14px", fontWeight: "600", color: isDark ? "#ffffff" : "#111827", marginBottom: "4px" }}>
                      Already Booked
                    </p>
                    <p style={{ fontSize: "12px", color: isDark ? "#9ca3af" : "#6b7280", marginBottom: "12px" }}>
                      You have already requested a lawyer for this case.
                    </p>
                    <button
                      onClick={() => setShowEscalateConfirm(false)}
                      style={{
                        width: "100%",
                        padding: "8px",
                        backgroundColor: isDark ? "#2a2a2a" : "#f3f4f6",
                        color: isDark ? "#9ca3af" : "#6b7280",
                        fontSize: "12px",
                        fontWeight: "700",
                        borderRadius: "8px",
                        border: "none",
                        cursor: "pointer"
                      }}
                    >
                      Close
                    </button>
                  </div>
                ) : (
                  <>
                    <p style={{ fontSize: "14px", marginBottom: "12px", fontWeight: "500", color: isDark ? "#d1d5db" : "#374151" }}>
                      Talk to a real lawyer about this case?
                    </p>
                    <div style={{ display: "flex", gap: "8px" }}>
                      <button
                        onClick={async () => {
                          setIsEscalating(true);
                          try {
                            await onEscalate();
                            setShowEscalateConfirm(false);
                            setShowSuccessToast(true);
                            setTimeout(() => setShowSuccessToast(false), 3000);
                          } catch (err) {
                            console.error("Escalation failed:", err);
                          } finally {
                            setIsEscalating(false);
                          }
                        }}
                        disabled={isEscalating}
                        style={{
                          flex: 1,
                          padding: "8px",
                          backgroundColor: "#2563eb",
                          color: "#ffffff",
                          fontSize: "12px",
                          fontWeight: "700",
                          borderRadius: "8px",
                          border: "none",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center"
                        }}
                      >
                        {isEscalating ? <Loader2 className="h-3 w-3 animate-spin" /> : "Confirm"}
                      </button>
                      <button
                        onClick={() => setShowEscalateConfirm(false)}
                        style={{
                          flex: 1,
                          padding: "8px",
                          backgroundColor: isDark ? "#2a2a2a" : "#f3f4f6",
                          color: isDark ? "#9ca3af" : "#6b7280",
                          fontSize: "12px",
                          fontWeight: "700",
                          borderRadius: "8px",
                          border: "none",
                          cursor: "pointer"
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            <button
              type="button"
              onClick={() => {
                setShowEscalateConfirm(!showEscalateConfirm);
              }}
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "50%",
                border: "none",
                cursor: isBusy ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: isEscalated ? "rgba(59, 130, 246, 0.1)" : "transparent",
                color: isEscalated ? "#3B82F6" : (isDark ? "#9ca3af" : "#6b7280"),
                flexShrink: 0,
                opacity: isBusy ? 0.4 : 1,
              }}
              title={isEscalated ? "Lawyer Already Requested" : "Talk to Lawyer"}
            >
              {isEscalated ? <CheckCircle size={18} /> : <Scale size={18} />}
            </button>
          </div>
        )}

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