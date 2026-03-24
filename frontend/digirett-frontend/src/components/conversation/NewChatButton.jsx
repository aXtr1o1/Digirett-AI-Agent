import React from 'react';
import { Plus } from 'lucide-react';
import Button from '../common/Button';

const NewChatButton = ({ onClick }) => {
  return (
    <Button
      onClick={onClick}
      variant="primary"
      className="w-full flex items-center justify-center space-x-2"
    >
      <Plus className="h-5 w-5" />
      <span>New Chat</span>
    </Button>
  );
};

export default NewChatButton;
