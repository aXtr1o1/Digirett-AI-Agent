import React from 'react';
import { ExternalLink, FileText } from 'lucide-react';

const SourceLinks = ({ sources }) => {
  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 pt-4 border-t border-gray-200">
      <div className="flex items-center space-x-2 mb-2">
        <FileText className="h-4 w-4 text-gray-500" />
        <span className="text-sm font-medium text-gray-700">Sources:</span>
      </div>
      <div className="space-y-2">
        {sources.map((source, index) => (
          <a
            key={index}
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center space-x-2 text-sm text-primary-600 hover:text-primary-800 hover:underline group"
          >
            <ExternalLink className="h-3 w-3 flex-shrink-0" />
            <span className="truncate">
              {source.title || source.url}
            </span>
          </a>
        ))}
      </div>
    </div>
  );
};

export default SourceLinks;
