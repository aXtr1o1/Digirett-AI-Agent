import React, { useState, useEffect } from "react";
import { AlertTriangle } from "lucide-react";

const ErrorMessage = ({ message, onRetry, className = "" }) => {
  const [isOpen, setIsOpen] = useState(true);
  
  if (!message) return null;

  let messageText = typeof message === 'string' ? message : message.message || String(message);
  if (messageText.includes("Connection lost") || messageText.includes("Connection error") || messageText.includes("Stream error")) {
    messageText = "Message limit reached. Your session resets every 4 hours.";
  }

  // Re-open if the error message changes
  useEffect(() => {
    if (messageText) {
      setIsOpen(true);
    }
  }, [messageText]);

  // Bind Enter and Escape keys for seamless accessibility
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === "Enter" || e.key === "Escape") {
        e.preventDefault();
        handleClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, messageText]);

  const handleClose = () => {
    setIsOpen(false);
    if (onRetry) {
      onRetry();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 z-[9999] flex items-center justify-center p-4">
      {/* Click outside to close (standard premium modal feature) */}
      <div className="absolute inset-0" onClick={handleClose} />
      
      {/* Premium Dialog Card */}
      <div className="relative bg-[#0d0d0d] border border-red-500/10 max-w-md w-full rounded-[28px] p-6 sm:p-8 shadow-2xl flex flex-col items-center text-center space-y-6 animate-in fade-in zoom-in duration-200">
        
        {/* Animated Warning Icon with Glow */}
        <div className="bg-[#ff4444]/10 p-4 rounded-full border border-[#ff4444]/20 text-[#ff4444] shadow-[0_0_20px_rgba(255,68,68,0.15)]">
          <AlertTriangle className="h-8 w-8 animate-pulse" />
        </div>

        {/* Text Section */}
        <div className="space-y-2">
          <h3 className="text-white font-extrabold text-lg sm:text-xl tracking-tight">
            System Notification
          </h3>
          <p className="text-gray-400 text-sm leading-relaxed font-medium px-2 max-h-[200px] overflow-y-auto">
            {messageText}
          </p>
        </div>

        {/* Footer Actions */}
        <div className="w-full pt-2">
          <button
            onClick={handleClose}
            className="w-full bg-white text-black hover:bg-gray-100 transition-all py-3 rounded-2xl font-extrabold text-sm tracking-tight active:scale-[0.97] duration-150 shadow-lg cursor-pointer"
          >
            OK
          </button>
        </div>

      </div>
    </div>
  );
};

export default ErrorMessage;
