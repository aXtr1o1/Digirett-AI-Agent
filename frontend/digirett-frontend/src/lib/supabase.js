import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

/**
 * Helper to get a Supabase client with the Clerk auth token.
 * This allows Supabase to respect Row Level Security (RLS) based on the Clerk user.
 * @param {Function} getToken - Clerk's getToken function
 */
export async function getSupabaseClient(getToken) {
  const token = await getToken({ template: 'supabase' });
  
  if (!token) return supabase;

  console.log("CLERK JWT FOR SUPABASE:", token);

  return createClient(supabaseUrl, supabaseAnonKey, {
    global: {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  });
}
