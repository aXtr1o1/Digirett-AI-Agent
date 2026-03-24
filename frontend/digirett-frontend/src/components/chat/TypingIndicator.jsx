import React from 'react';
import { Bot } from 'lucide-react';

const TypingIndicator = ({ theme = 'dark' }) => {
  const isDark = theme === 'dark';

  return (
    <div className="flex items-start space-x-3 mb-6">
      <div className={`flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center ${
        isDark ? 'bg-white' : 'bg-black'
      }`}>
        <Bot className={`h-6 w-6 ${isDark ? 'text-black' : 'text-white'}`} />
      </div>
      
      <div className={`
        rounded-2xl px-4 py-3
        ${isDark 
          ? 'bg-[#1a1a1a] border border-gray-800' 
          : 'bg-white border border-gray-200'
        }
      `}>
        <div className="flex space-x-1">
          <div className={`w-2 h-2 rounded-full animate-bounce ${isDark ? 'bg-white' : 'bg-gray-900'}`} style={{ animationDelay: '0ms' }} />
          <div className={`w-2 h-2 rounded-full animate-bounce ${isDark ? 'bg-white' : 'bg-gray-900'}`} style={{ animationDelay: '150ms' }} />
          <div className={`w-2 h-2 rounded-full animate-bounce ${isDark ? 'bg-white' : 'bg-gray-900'}`} style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  );
};

export default TypingIndicator;
