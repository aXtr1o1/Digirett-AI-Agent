-- Create the user_memories table
CREATE TABLE IF NOT EXISTS public.user_memories (
    memory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    fact TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Index for fast lookup by user_id
CREATE INDEX IF NOT EXISTS user_memories_user_id_idx ON public.user_memories(user_id);

-- Enable RLS (Row Level Security)
ALTER TABLE public.user_memories ENABLE ROW LEVEL SECURITY;

-- Create policies (Assuming service role has full access, and you might want users to only access their own)
CREATE POLICY "Users can read own memories"
    ON public.user_memories FOR SELECT
    USING (auth.uid() = user_id);

-- Note: The backend uses the service_role key, so it bypasses RLS by default.
