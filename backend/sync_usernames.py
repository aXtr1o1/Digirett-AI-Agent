import sys, os, httpx
sys.path.append('d:/axtrlabs/Digirett-AI-Agent/backend')
from config import settings
import db.supabase_client

db.supabase_client.supabase_client.connect(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
supabase = db.supabase_client.get_supabase()

resp = supabase.table('users').select('user_id, clerk_user_id, email, user_name, role').execute()

headers = {'Authorization': f'Bearer {settings.CLERK_SECRET_KEY}'}

for u in resp.data:
    clerk_id = u['clerk_user_id']
    if not clerk_id: continue
    
    clerk_resp = httpx.get(f'https://api.clerk.com/v1/users/{clerk_id}', headers=headers)
    if clerk_resp.status_code == 200:
        c_data = clerk_resp.json()
        c_username = c_data.get('username')
        
        if c_username and c_username != u['user_name']:
            print(f"UPDATING {u['email']}: '{u['user_name']}' -> '{c_username}'")
            supabase.table('users').update({'user_name': c_username}).eq('user_id', u['user_id']).execute()
            
print('Done!')
