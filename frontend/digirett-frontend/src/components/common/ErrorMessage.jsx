import React, { useEffect } from "react";

const ErrorMessage = ({ message, onRetry, className = "" }) => {
  if (!message) return null;

  const messageText = typeof message === 'string' ? message : message.message || String(message);

  // 🚨 Reverting to Native Browser Alert as per user request (2nd screenshot style)
  useEffect(() => {
    if (messageText) {
      // Prevents duplicate alerts for the same error state
      if (!window.activeAlertMessage || window.activeAlertMessage !== messageText) {
        window.activeAlertMessage = messageText;
        window.alert(messageText);
        setTimeout(() => { window.activeAlertMessage = null; }, 2000);
      }
    }
  }, [messageText]);

  // Return null to suppress the red error banner in the UI
  return null;
};

export default ErrorMessage;
