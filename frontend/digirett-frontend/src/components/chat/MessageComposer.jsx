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
    <div className="px-4 py-4 bg-black">
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
        
        {/* 🔹 INPUT CONTAINER */}
        <div className="flex items-end gap-3 bg-[#1a1a1a] rounded-2xl px-4 py-3">

          {/* TEXTAREA */}
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything..."
            disabled={disabled}
            rows={1}
            className="
              flex-1
              bg-transparent
              resize-none
              overflow-hidden
              text-white
              placeholder-gray-500
              caret-white
              focus:outline-none
            "
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
              className="
                h-10 w-10
                rounded-xl
                bg-white
                text-black
                flex items-center justify-center
                hover:bg-gray-200
                transition
                disabled:opacity-50
                disabled:cursor-not-allowed
              "
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
