import React from 'react';
import { ExternalLink, FileText } from 'lucide-react';

const SourceLinks = ({ sources, theme = 'dark' }) => {
  const isDark = theme === 'dark';

  if (!Array.isArray(sources) || sources.length === 0) {
    return null;
  }

  return (
    <div
      className={`mt-4 pt-4 border-t ${
        isDark ? 'border-gray-700' : 'border-gray-200'
      }`}
    >
      <div className="flex items-center space-x-2 mb-3">
        <FileText
          className={`h-4 w-4 ${
            isDark ? 'text-gray-400' : 'text-gray-500'
          }`}
        />
        <span
          className={`text-xs font-semibold uppercase tracking-wide ${
            isDark ? 'text-gray-400' : 'text-gray-500'
          }`}
        >
          Sources
        </span>
      </div>

      <div className="space-y-2">
        {sources.map((source) => {
          const uniqueKey = source.url || source.title;

          return (
            <a
              key={uniqueKey}
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className={`group block p-3 rounded-lg border transition-all duration-200 ${
                isDark
                  ? 'bg-[#111111] border-gray-800 hover:border-blue-500 hover:bg-[#161616]'
                  : 'bg-gray-50 border-gray-200 hover:border-blue-400 hover:bg-blue-50'
              }`}
            >
              <div className="flex items-center justify-between">
                <span
                  className={`text-sm truncate ${
                    isDark
                      ? 'text-blue-400 group-hover:text-blue-300'
                      : 'text-blue-600 group-hover:text-blue-500'
                  }`}
                >
                  {source.title || source.url}
                </span>

                <ExternalLink
                  className={`h-4 w-4 transition-colors ${
                    isDark
                      ? 'text-gray-500 group-hover:text-blue-400'
                      : 'text-gray-400 group-hover:text-blue-500'
                  }`}
                />
              </div>
            </a>
          );
        })}
      </div>
    </div>
  );
};

export default SourceLinks;