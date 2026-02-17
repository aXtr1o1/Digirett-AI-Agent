import React from 'react';
import { User, Bot, Copy, Check } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import SourceLinks from './SourceLinks';
import useCopyToClipboard from '../../hooks/useCopyToClipboard';

const Message = ({ message, isStreaming = false, theme = 'dark' }) => {
  const { isCopied, copyToClipboard } = useCopyToClipboard();
  const isUser = message.role === 'user';
  const isDark = theme === 'dark';

  const handleCopy = () => {
    copyToClipboard(message.content);
  };

  return (
    <div className={`flex items-start space-x-3 ${isUser ? 'justify-end' : 'justify-start'} mb-6`}>
      {!isUser && (
        <div className={`flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center ${
          isDark ? 'bg-white' : 'bg-black'
        }`}>
          <Bot className={`h-6 w-6 ${isDark ? 'text-black' : 'text-white'}`} />
        </div>
      )}

      <div className={`flex-1 max-w-3xl ${isUser ? 'flex justify-end' : ''}`}>
        <div
          className={`
            rounded-2xl px-4 py-3
            ${isUser 
              ? isDark 
                ? 'bg-[#2a2a2a] text-white' 
                : 'bg-gray-200 text-gray-900'
              : isDark
                ? 'bg-[#1a1a1a] border border-gray-800 text-gray-100'
                : 'bg-white border border-gray-200 text-gray-900'
            }
          `}
        >
          {/* Message content */}
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
          ) : (
            <div className={`prose prose-sm max-w-none ${isDark ? 'prose-invert' : 'prose-light'}`}>
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}

          {/* Copy button for assistant messages */}
          {!isUser && !isStreaming && (
            <button
              onClick={handleCopy}
              className={`
                mt-3 flex items-center space-x-1 text-xs transition-colors
                ${isDark 
                  ? 'text-gray-500 hover:text-gray-300' 
                  : 'text-gray-500 hover:text-gray-700'
                }
              `}
            >
              {isCopied ? (
                <>
                  <Check className="h-3 w-3" />
                  <span>Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  <span>Copy</span>
                </>
              )}
            </button>
          )}

          {/* Source links */}
          {!isUser && message.sources && message.sources.length > 0 && (
            <SourceLinks sources={message.sources} theme={theme} />
          )}
        </div>
      </div>

      {isUser && (
        <div className={`flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center ${
          isDark ? 'bg-gray-700' : 'bg-gray-300'
        }`}>
          <User className={`h-5 w-5 ${isDark ? 'text-gray-300' : 'text-gray-600'}`} />
        </div>
      )}
    </div>
  );
};

export default Message;