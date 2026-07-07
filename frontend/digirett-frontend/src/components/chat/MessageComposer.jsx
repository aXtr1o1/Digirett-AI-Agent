import React, { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { StopCircle, Paperclip, ArrowUp, X, Scale, Check, CheckCircle, Loader2 } from "lucide-react";

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
  messageCount = 0,
}) => {
  const [message, setMessage] = useState("");
  const [file, setFile] = useState(null);
  const [showEscalateConfirm, setShowEscalateConfirm] = useState(false);
  const [isEscalating, setIsEscalating] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const handleHeightUpdate = () => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      if (rect.height > 0) {
        document.documentElement.style.setProperty("--composer-height", `${rect.height}px`);
      }
    };
    handleHeightUpdate();

    const observer = new ResizeObserver(() => {
      handleHeightUpdate();
    });
    observer.observe(containerRef.current);

    return () => observer.disconnect();
  }, []);
  const [showSuccessToast, setShowSuccessToast] = useState(false);
  const [localEscalated, setLocalEscalated] = useState(false);
  const [escalatePriority, setEscalatePriority] = useState("normal");
  const [escalateUrgentReason, setEscalateUrgentReason] = useState("");
  const [escalateError, setEscalateError] = useState("");

  // Sync localEscalated state with parent isEscalated prop
  useEffect(() => {
    if (!isEscalated) {
      setLocalEscalated(false);
      setShowEscalateConfirm(false);
    }
  }, [isEscalated]);

  // Reset form and errors when modal is opened
  useEffect(() => {
    if (showEscalateConfirm) {
      setEscalateError("");
      setEscalatePriority("normal");
      setEscalateUrgentReason("");
    }
  }, [showEscalateConfirm]);

  const isBusy = disabled || isProcessingDoc;
  const isInputBlocked = isBusy || (disabled && !isStreaming);

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
    if (file) return "Add a question about the document";
    return "Ask Anything...";
  };

  return (
    <div
      ref={containerRef}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "6px",
      }}
    >
      {/* Escalation Confirm Inline Card */}
      {showEscalateConfirm && (
        <div style={{
          maxWidth: "480px",
          width: "100%",
          margin: "0 auto 8px 0",
          padding: "16px 20px",
          borderRadius: "16px",
          backgroundColor: isDark ? "rgba(30, 41, 59, 0.9)" : "#ffffff",
          border: isDark ? "1px solid rgba(59, 130, 246, 0.25)" : "1px solid rgba(59, 130, 246, 0.2)",
          boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
          backdropFilter: "blur(12px)",
          animation: "toastIn 0.25s ease-out forwards",
        }}>
          {isEscalated || localEscalated ? (
            <div style={{ textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center" }}>
              <CheckCircle size={24} style={{ color: "#2563eb", marginBottom: "8px" }} />
              <p style={{ fontSize: "14px", fontWeight: "700", color: isDark ? "#ffffff" : "#111827", marginBottom: "4px" }}>
                Already Booked
              </p>
              <p style={{ fontSize: "12px", color: isDark ? "#9ca3af" : "#6b7280", marginBottom: "12px", lineHeight: "1.4" }}>
                You have already requested a legal consultation for this matter.
              </p>
              <button
                onClick={() => setShowEscalateConfirm(false)}
                style={{
                  width: "100%",
                  padding: "8px",
                  backgroundColor: isDark ? "#1f2937" : "#f3f4f6",
                  color: isDark ? "#d1d5db" : "#4b5563",
                  fontSize: "11px",
                  fontWeight: "700",
                  borderRadius: "8px",
                  border: "none",
                  cursor: "pointer",
                  transition: "all 0.2s"
                }}
              >
                Close
              </button>
            </div>
          ) : (
            <>
              <p style={{ fontSize: "13px", marginBottom: "12px", fontWeight: "700", color: isDark ? "#f3f4f6" : "#1f2937", lineHeight: "1.4", textAlign: "left" }}>
                Would you like to consult with a professional regarding this matter?
              </p>

              {/* Error Message */}
              {escalateError && (
                <div style={{
                  padding: "8px 10px",
                  backgroundColor: isDark ? "rgba(239, 68, 68, 0.1)" : "rgba(239, 68, 68, 0.05)",
                  border: "1px solid rgba(239, 68, 68, 0.2)",
                  borderRadius: "10px",
                  color: "#f87171",
                  fontSize: "10px",
                  fontWeight: "600",
                  marginBottom: "12px",
                  lineHeight: "1.4",
                  textAlign: "left"
                }}>
                  {escalateError}
                </div>
              )}

              <div style={{ display: "flex", gap: "8px" }}>
                <button
                  onClick={async () => {
                    setIsEscalating(true);
                    setEscalateError("");
                    try {
                      await onEscalate("", "normal", null);
                      setLocalEscalated(true);
                      setShowEscalateConfirm(false);
                      setShowSuccessToast(true);
                      setTimeout(() => setShowSuccessToast(false), 3000);
                    } catch (err) {
                      console.error("Escalation failed:", err);
                      setEscalateError(err.message || "Failed to escalate. Please try again.");
                    } finally {
                      setIsEscalating(false);
                    }
                  }}
                  disabled={isEscalating}
                  style={{
                    flex: 1,
                    padding: "8px 12px",
                    backgroundColor: "#2563eb",
                    color: "#ffffff",
                    fontSize: "11px",
                    fontWeight: "700",
                    borderRadius: "8px",
                    border: "none",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    transition: "all 0.2s"
                  }}
                >
                  {isEscalating ? <Loader2 className="h-3 w-3 animate-spin" /> : "Confirm"}
                </button>
                <button
                  onClick={() => setShowEscalateConfirm(false)}
                  disabled={isEscalating}
                  style={{
                    flex: 1,
                    padding: "8px 12px",
                    backgroundColor: isDark ? "#1f2937" : "#f3f4f6",
                    color: isDark ? "#d1d5db" : "#4b5563",
                    fontSize: "11px",
                    fontWeight: "700",
                    borderRadius: "8px",
                    border: "none",
                    cursor: "pointer",
                    transition: "all 0.2s"
                  }}
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      )}

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
            <span style={{ fontSize: "14px", fontWeight: "600" }}>
              {isEscalated || localEscalated
                ? "You have successfully scheduled a consultation"
                : "Request submitted. Lawyer will contact you shortly."}
            </span>
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
            {/* Lawyer Escalation Confirm Modal (Old portal-based popup overlay) is now moved to the bottom of this file as a standard comment block */}

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
                backgroundColor: (isEscalated || localEscalated) ? "rgba(59, 130, 246, 0.1)" : "transparent",
                color: (isEscalated || localEscalated) ? "#3B82F6" : (isDark ? "#9ca3af" : "#6b7280"),
                flexShrink: 0,
                opacity: isBusy ? 0.4 : 1,
              }}
              title={(isEscalated || localEscalated) ? "" : "Talk to Lawyer"}
            >
              {(isEscalated || localEscalated) ? (
                <CheckCircle size={22} style={{ color: "#2563eb" }} />
              ) : (
                <Scale size={18} />
              )}
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
          disabled={isBusy}
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
        {isStreaming || isProcessingDoc ? (
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

/*
OLD PORTAL-BASED ESCALATION CONFIRM MODAL (PRESERVED CODE BLOCK):

{showEscalateConfirm && createPortal(
  <div style={{
    position: "fixed",
    inset: 0,
    backgroundColor: isDark ? "rgba(0, 0, 0, 0.6)" : "rgba(0, 0, 0, 0.4)",
    backdropFilter: "blur(4px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 9999,
  }}>
    <div style={{
      width: "420px",
      maxWidth: "90%",
      padding: "24px",
      borderRadius: "24px",
      boxShadow: "0 20px 40px rgba(0, 0, 0, 0.3)",
      backgroundColor: isDark ? "#111827" : "#ffffff",
      border: isDark ? "1px solid #1f2937" : "1px solid #e5e7eb",
    }}>
      {isEscalated || localEscalated ? (
        <div style={{ textAlign: "center" }}>
          <CheckCircle size={32} style={{ color: "#2563eb", marginBottom: "12px" }} />
          <p style={{ fontSize: "16px", fontWeight: "600", color: isDark ? "#ffffff" : "#111827", marginBottom: "6px" }}>
            Already Booked
          </p>
          <p style={{ fontSize: "13px", color: isDark ? "#9ca3af" : "#6b7280", marginBottom: "16px", lineHeight: "1.5" }}>
            You have already requested a legal consultation for this matter.
          </p>
          <button
            onClick={() => setShowEscalateConfirm(false)}
            style={{
              width: "100%",
              padding: "10px",
              backgroundColor: isDark ? "#1f2937" : "#f3f4f6",
              color: isDark ? "#d1d5db" : "#4b5563",
              fontSize: "12px",
              fontWeight: "700",
              borderRadius: "10px",
              border: "none",
              cursor: "pointer",
              transition: "all 0.2s"
            }}
          >
            Close
          </button>
        </div>
      ) : (
        <>
          <p style={{ fontSize: "15px", marginBottom: "20px", fontWeight: "700", color: isDark ? "#f3f4f6" : "#1f2937", lineHeight: "1.4" }}>
          Would you like to consult with a professional regarding this matter?
        </p>

        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", fontSize: "10px", fontWeight: "800", color: isDark ? "#9ca3af" : "#6b7280", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Select Priority
          </label>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {[
              { 
                value: "normal", 
                label: "Normal", 
                desc: "Routine legal questions or document review.",
                dotColor: isDark ? "#64748b" : "#94a3b8",
                activeBorder: isDark ? "#9ca3af" : "#4b5563",
                activeBg: isDark ? "rgba(156, 163, 175, 0.05)" : "rgba(107, 114, 128, 0.03)"
              },
              { 
                value: "high", 
                label: "High", 
                desc: "Important issue that should be handled soon.",
                dotColor: "#f59e0b",
                activeBorder: "#f59e0b",
                activeBg: isDark ? "rgba(245, 158, 11, 0.05)" : "rgba(245, 158, 11, 0.03)"
              },
              { 
                value: "urgent", 
                label: "Urgent", 
                desc: "Immediate legal emergency.",
                dotColor: "#ef4444",
                activeBorder: "#ef4444",
                activeBg: isDark ? "rgba(239, 68, 68, 0.05)" : "rgba(239, 68, 68, 0.03)"
              }
            ].map((p) => {
              const isActive = escalatePriority === p.value;
              return (
                <div
                  key={p.value}
                  onClick={() => {
                    setEscalatePriority(p.value);
                    if (p.value !== "urgent") setEscalateUrgentReason("");
                  }}
                  style={{
                    display: "flex",
                    alignItems: "start",
                    gap: "10px",
                    padding: "10px 12px",
                    borderRadius: "12px",
                    border: isActive ? `1.5px solid ${p.activeBorder}` : (isDark ? "1px solid #1f2937" : "1px solid #e5e7eb"),
                    backgroundColor: isActive ? p.activeBg : "transparent",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", height: "16px", marginTop: "2px" }}>
                    <span style={{
                      height: "8px",
                      width: "8px",
                      borderRadius: "50%",
                      backgroundColor: p.dotColor,
                      boxShadow: isActive ? `0 0 8px ${p.dotColor}` : "none",
                      display: "inline-block"
                    }} />
                  </div>
                  <div style={{ flex: 1, textAlign: "left" }}>
                    <div style={{ 
                      fontSize: "12px", 
                      fontWeight: "700", 
                      color: isActive 
                        ? (isDark ? "#f3f4f6" : "#1f2937") 
                        : (isDark ? "#9ca3af" : "#4b5563") 
                    }}>
                      {p.label}
                    </div>
                    <div style={{ 
                      fontSize: "10px", 
                      fontWeight: "500", 
                      color: isDark ? "#6b7280" : "#9ca3af",
                      marginTop: "2px",
                      lineHeight: "1.3"
                    }}>
                      {p.desc}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ 
          fontSize: "9px", 
          color: isDark ? "#9ca3af" : "#4b5563", 
          lineHeight: "1.4", 
          marginTop: "12px", 
          marginBottom: "16px",
          padding: "10px",
          borderRadius: "8px",
          backgroundColor: isDark ? "rgba(255, 255, 255, 0.02)" : "rgba(0, 0, 0, 0.02)",
          border: isDark ? "1px solid rgba(255, 255, 255, 0.05)" : "1px solid rgba(0, 0, 0, 0.05)",
          textAlign: "left"
        }}>
          <span style={{ fontWeight: "700", color: isDark ? "#f3f4f6" : "#1f2937" }}>Please note:</span> The assigned legal professional will review the details of your matter and may adjust the priority level based on their assessment of its urgency.
        </div>

        {escalatePriority === "urgent" && (
          <div style={{ marginBottom: "16px" }}>
            <label style={{ display: "block", fontSize: "10px", fontWeight: "800", color: isDark ? "#fca5a5" : "#ef4444", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Urgent Reason <span style={{ color: "#ef4444" }}>*</span>
            </label>
            <textarea
              value={escalateUrgentReason}
              onChange={(e) => setEscalateUrgentReason(e.target.value)}
              placeholder="Please describe why this is urgent..."
              rows={2}
              style={{
                width: "100%",
                padding: "10px",
                borderRadius: "10px",
                border: isDark ? "1.5px solid #ef4444" : "1.5px solid #fca5a5",
                backgroundColor: isDark ? "#111827" : "#fff",
                color: isDark ? "#fca5a5" : "#991b1b",
                fontSize: "12px",
                resize: "none",
                outline: "none",
                lineHeight: "1.4",
                fontFamily: "inherit"
              }}
            />
          </div>
        )}

        {escalateError && (
          <div style={{
            padding: "10px 12px",
            backgroundColor: isDark ? "rgba(239, 68, 68, 0.1)" : "rgba(239, 68, 68, 0.05)",
            border: "1px solid rgba(239, 68, 68, 0.2)",
            borderRadius: "12px",
            color: "#f87171",
            fontSize: "11px",
            fontWeight: "600",
            marginBottom: "16px",
            lineHeight: "1.4",
            textAlign: "left"
          }}>
            {escalateError}
          </div>
        )}

        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={async () => {
              if (escalatePriority === "urgent" && !escalateUrgentReason.trim()) {
                return;
              }
              setIsEscalating(true);
              setEscalateError("");
              try {
                await onEscalate("", escalatePriority, escalatePriority === "urgent" ? escalateUrgentReason : null);
                setLocalEscalated(true);
                setShowEscalateConfirm(false);
                setShowSuccessToast(true);
                setTimeout(() => setShowSuccessToast(false), 3000);
              } catch (err) {
                console.error("Escalation failed:", err);
                setEscalateError(err.message || "Failed to escalate. Please try again.");
              } finally {
                setIsEscalating(false);
              }
            }}
            disabled={isEscalating || (escalatePriority === "urgent" && !escalateUrgentReason.trim())}
            style={{
              flex: 1,
              padding: "10px",
              backgroundColor: (escalatePriority === "urgent" && !escalateUrgentReason.trim()) 
                ? (isDark ? "#1f2937" : "#f3f4f6") 
                : "#2563eb",
              color: (escalatePriority === "urgent" && !escalateUrgentReason.trim()) 
                ? (isDark ? "#4b5563" : "#9ca3af") 
                : "#ffffff",
              fontSize: "12px",
              fontWeight: "700",
              borderRadius: "10px",
              border: "none",
              cursor: (escalatePriority === "urgent" && !escalateUrgentReason.trim()) ? "default" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "all 0.2s"
            }}
          >
            {isEscalating ? <Loader2 className="h-3 w-3 animate-spin" /> : "Confirm"}
          </button>
          <button
            onClick={() => setShowEscalateConfirm(false)}
            style={{
              flex: 1,
              padding: "10px",
              backgroundColor: isDark ? "#1f2937" : "#f3f4f6",
              color: isDark ? "#d1d5db" : "#4b5563",
              fontSize: "12px",
              fontWeight: "700",
              borderRadius: "10px",
              border: "none",
              cursor: "pointer",
              transition: "all 0.2s"
            }}
          >
            Cancel
          </button>
        </div>
      </>
    )}
  </div>
</div>,
document.body
)}
*/

export default MessageComposer;