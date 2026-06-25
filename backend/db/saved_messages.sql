-- Create saved_messages table to store bookmarked messages
CREATE TABLE IF NOT EXISTS saved_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    note TEXT DEFAULT '',
    saved_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT unique_user_message UNIQUE (user_id, message_id)
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_saved_messages_user_id ON saved_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_messages_message_id ON saved_messages(message_id);
