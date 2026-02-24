import React from "react";
import { User, Bot, Copy, Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import SourceLinks from "./SourceLinks";
import useCopyToClipboard from "../../hooks/useCopyToClipboard";

const Message = ({ message, isStreaming = false, theme = "dark" }) => {
  const { isCopied, copyToClipboard } = useCopyToClipboard();
  const isUser = message.role === "user";
  const isDark = theme === "dark";

  return (
    <div className={`flex gap-4 mb-6 ${isUser ? "justify-end" : "justify-start"}`}>

      {/* ASSISTANT AVATAR */}
      {!isUser && (
        <div
          className={`flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center mt-1 ${
            isDark ? "bg-white" : "bg-gray-900"
          }`}
        >
          <Bot className={`h-4 w-4 ${isDark ? "text-black" : "text-white"}`} />
        </div>
      )}

      {/* MESSAGE BODY */}
      <div className={`flex flex-col min-w-0 ${isUser ? "items-end max-w-[85%]" : "flex-1"}`}>

        {/* USER MESSAGE */}
        {isUser ? (
          <div
            className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words ${
              isDark ? "bg-[#2f2f2f] text-white" : "bg-gray-100 text-gray-900"
            }`}
          >
            {message.content}
          </div>
        ) : (

          /* ASSISTANT MESSAGE */
          <div className={`text-sm leading-7 break-words w-full ${isDark ? "text-gray-100" : "text-gray-800"}`}>

            {isStreaming ? (

              <div className="whitespace-pre-wrap text-sm leading-7">
                {message.content}
              </div>

            ) : (

              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{

                  /* ✅ TABLE SUPPORT ADDED */
                  table: (props) => (
                    <div className="overflow-x-auto my-4">
                      <table
                        className={`border-collapse w-full text-sm ${
                          isDark ? "border-gray-700" : "border-gray-300"
                        }`}
                        {...props}
                      />
                    </div>
                  ),

                  tr: (props) => (
                    <tr
                      className={
                        isDark
                          ? "border-b border-gray-700"
                          : "border-b border-gray-200"
                      }
                      {...props}
                    />
                  ),

                  th: (props) => (
                    <th
                      className={`px-3 py-2 text-left font-semibold border ${
                        isDark
                          ? "border-gray-700 bg-gray-800"
                          : "border-gray-300 bg-gray-100"
                      }`}
                      {...props}
                    />
                  ),

                  td: (props) => (
                    <td
                      className={`px-3 py-2 border ${
                        isDark ? "border-gray-700" : "border-gray-300"
                      }`}
                      {...props}
                    />
                  ),

                  /* EXISTING MARKDOWN STYLES */

                  h1: (props) => (
                    <h1 className="text-2xl font-bold mt-6 mb-3 leading-tight" {...props} />
                  ),
                  h2: (props) => (
                    <h2 className="text-xl font-bold mt-5 mb-2 leading-tight" {...props} />
                  ),
                  h3: (props) => (
                    <h3 className="text-lg font-semibold mt-4 mb-2 leading-tight" {...props} />
                  ),
                  p: (props) => (
                    <p className="mb-4 text-sm leading-7" {...props} />
                  ),
                  ul: (props) => (
                    <ul className="list-disc pl-6 mb-4 space-y-1 text-sm" {...props} />
                  ),
                  ol: (props) => (
                    <ol className="list-decimal pl-6 mb-4 space-y-1 text-sm" {...props} />
                  ),
                  li: (props) => (
                    <li className="text-sm leading-6" {...props} />
                  ),
                  a: (props) => (
                    <a
                      className="text-blue-500 hover:underline"
                      target="_blank"
                      rel="noopener noreferrer"
                      {...props}
                    />
                  ),
                  strong: (props) => (
                    <strong className="font-semibold" {...props} />
                  ),

                  code({ inline, children }) {
                    if (inline) {
                      return (
                        <code
                          className={`px-1.5 py-0.5 rounded text-xs font-mono ${
                            isDark
                              ? "bg-gray-700 text-gray-200"
                              : "bg-gray-100 text-gray-800"
                          }`}
                        >
                          {children}
                        </code>
                      );
                    }
                    return (
                      <pre
                        className={`rounded-xl p-4 my-3 overflow-x-auto text-xs font-mono ${
                          isDark
                            ? "bg-gray-900 text-gray-200"
                            : "bg-gray-50 text-gray-800"
                        }`}
                      >
                        <code>{children}</code>
                      </pre>
                    );
                  },

                  hr: () => (
                    <hr className={`my-4 ${isDark ? "border-gray-700" : "border-gray-200"}`} />
                  ),
                }}
              >
                {message.content}
              </ReactMarkdown>

            )}

            {/* COPY BUTTON */}
            {!isStreaming && (
              <button
                onClick={() => copyToClipboard(message.content)}
                className={`mt-1 flex items-center gap-1.5 text-xs ${
                  isDark
                    ? "text-gray-500 hover:text-gray-300"
                    : "text-gray-400 hover:text-gray-600"
                }`}
              >
                {isCopied ? (
                  <>
                    <Check className="h-3 w-3" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" />
                    <span>Copy</span>
                  </>
                )}
              </button>
            )}

            {/* SOURCES */}
            {!isStreaming &&
              message.sources &&
              message.sources.length > 0 && (
                <SourceLinks sources={message.sources} theme={theme} />
              )}

          </div>
        )}
      </div>

      {/* USER AVATAR */}
      {isUser && (
        <div
          className={`flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center mt-1 ${
            isDark ? "bg-gray-600" : "bg-gray-300"
          }`}
        >
          <User className={`h-4 w-4 ${isDark ? "text-gray-200" : "text-gray-600"}`} />
        </div>
      )}

    </div>
  );
};

export default Message;