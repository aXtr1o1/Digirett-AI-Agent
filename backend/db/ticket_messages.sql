-- Create ticket_messages table to store pre-consultation messages
CREATE TABLE IF NOT EXISTS ticket_messages (
    message_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id   UUID NOT NULL REFERENCES hitl_tickets(ticket_id) ON DELETE CASCADE,
    sender_id   UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    sender_role TEXT NOT NULL CHECK (sender_role IN ('user', 'lawyer')),
    content     TEXT NOT NULL,
    file_name   TEXT,
    document_id UUID,
    is_read     BOOLEAN DEFAULT FALSE NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id ON ticket_messages(ticket_id);
CREATE INDEX IF NOT EXISTS idx_ticket_messages_is_read ON ticket_messages(is_read) WHERE is_read = FALSE;
