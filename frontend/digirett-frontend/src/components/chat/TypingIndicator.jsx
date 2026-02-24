import React from "react";
import { Bot } from "lucide-react";

const TypingIndicator = ({ theme = "dark" }) => {
  const isDark = theme === "dark";

  return (
    <div className="flex items-start space-x-3 mb-6">

      {/* Avatar */}
      <div
        className={`flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center ${
          isDark ? "bg-white" : "bg-black"
        }`}
      >
        <Bot className={`h-6 w-6 ${isDark ? "text-black" : "text-white"}`} />
      </div>

      {/* Thinking Bubble */}
      <div
        className={`
          rounded-2xl px-5 py-4 text-sm
          ${isDark
            ? "bg-[#1a1a1a] border border-gray-800 text-gray-300"
            : "bg-white border border-gray-200 text-gray-600"
          }
        `}
      >
        <div className="flex items-center gap-2">
          <span className="italic animate-pulse">Thinking</span>

          {/* animated dots */}
          <span className="flex gap-1">
            <span className="w-1 h-1 rounded-full bg-current animate-bounce" style={{ animationDelay: "0ms" }} />
            <span className="w-1 h-1 rounded-full bg-current animate-bounce" style={{ animationDelay: "150ms" }} />
            <span className="w-1 h-1 rounded-full bg-current animate-bounce" style={{ animationDelay: "300ms" }} />
          </span>
        </div>
      </div>
    </div>
  );
};

export default TypingIndicator;