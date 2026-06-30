-- Drop existing saved_messages table
DROP TABLE IF EXISTS saved_messages CASCADE;

-- Create library_documents table to store uploaded documents in the library
CREATE TABLE IF NOT EXISTS library_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    char_count INT DEFAULT 0,
    extracted_text TEXT DEFAULT '',
    note TEXT DEFAULT '',
    storage_path TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (now() + interval '30 days') NOT NULL
);

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_library_documents_user_id ON library_documents(user_id);
