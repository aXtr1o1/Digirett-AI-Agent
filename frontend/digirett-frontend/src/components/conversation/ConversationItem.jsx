import React from 'react';
import { MessageSquare, Trash2 } from 'lucide-react';

const ConversationItem = ({ 
  conversation, 
  isActive, 
  onClick,
  onDelete 
}) => {
  const handleDelete = (e) => {
    e.stopPropagation();
    if (window.confirm('Are you sure you want to delete this conversation?')) {
      onDelete(conversation.id || conversation.conversation_id);
    }
  };

  // Format timestamp
  const formatDate = (dateString) => {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString();
  };

  return (
    <div
      onClick={onClick}
      className={`
        group px-4 py-3 cursor-pointer transition-colors
        border-l-4 hover:bg-gray-50
        ${isActive 
          ? 'bg-primary-50 border-primary-600' 
          : 'bg-white border-transparent'
        }
      `}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start space-x-3 flex-1 min-w-0">
          <MessageSquare 
            className={`h-5 w-5 mt-0.5 flex-shrink-0 ${
              isActive ? 'text-primary-600' : 'text-gray-400'
            }`} 
          />
          <div className="flex-1 min-w-0">
            <p className={`
              text-sm font-medium truncate
              ${isActive ? 'text-primary-900' : 'text-gray-900'}
            `}>
              {conversation.title || 'New Conversation'}
            </p>
            <p className="text-xs text-gray-500 mt-0.5">
              {formatDate(conversation.updated_at || conversation.created_at)}
            </p>
          </div>
        </div>
        
        {onDelete && (
          <button
            onClick={handleDelete}
            className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-100 transition-opacity"
          >
            <Trash2 className="h-4 w-4 text-red-600" />
          </button>
        )}
      </div>
    </div>
  );
};

export default ConversationItem;
