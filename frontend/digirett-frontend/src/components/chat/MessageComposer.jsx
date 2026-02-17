import React, { useState, useRef, useEffect } from "react";
import { Send, StopCircle } from "lucide-react";

const MessageComposer = ({
  onSend,
  disabled,
  isStreaming,
  onStop,
  theme = "dark",
}) => {
  const [message, setMessage] = useState("");
  const textareaRef = useRef(null);
  const isDark = theme === "dark";

  /* =========================
     Auto resize textarea
  ========================= */
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 180) + "px";
    }
  }, [message]);

  /* =========================
     Auto focus cursor
  ========================= */
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  /* =========================
     Submit message
  ========================= */
  const handleSubmit = (e) => {
    e.preventDefault();
    if (message.trim() && !disabled) {
      onSend(message);
      setMessage("");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className={`px-4 py-4 ${isDark ? "bg-black" : "bg-gray-50"}`}>
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">

        {/* 🔹 INPUT CONTAINER */}
        <div className={`flex items-end gap-3 rounded-2xl px-4 py-3 border ${
          isDark
            ? "bg-[#1a1a1a] border-transparent"
            : "bg-white border-gray-200 shadow-sm"
        }`}>

          {/* TEXTAREA */}
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything..."
            disabled={disabled}
            rows={1}
            className={`
              flex-1
              bg-transparent
              resize-none
              overflow-hidden
              focus:outline-none
              ${isDark
                ? "text-white placeholder-gray-500 caret-white"
                : "text-gray-900 placeholder-gray-400 caret-gray-900"
              }
            `}
          />

          {/* BUTTON */}
          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              className="h-10 w-10 rounded-xl bg-red-600 hover:bg-red-700 flex items-center justify-center text-white"
            >
              <StopCircle size={18} />
            </button>
          ) : (
            <button
              type="submit"
              disabled={disabled || !message.trim()}
              className={`
                h-10 w-10 rounded-xl flex items-center justify-center transition
                disabled:opacity-50 disabled:cursor-not-allowed
                ${isDark
                  ? "bg-white text-black hover:bg-gray-200"
                  : "bg-gray-900 text-white hover:bg-gray-700"
                }
              `}
            >
              <Send size={18} />
            </button>
          )}
        </div>
      </form>
    </div>
  );
};

export default MessageComposer;