import asyncio
import logging
import sys

# Set absolute path to import backend modules
backend_dir = r"c:\Users\ELCOT\Digirett-AI-Agent\backend"
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from config import settings
from services.email_service import EmailService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test():
    print("Initializing EmailService with config:")
    print("SMTP_HOST:", settings.SMTP_HOST)
    print("SMTP_PORT:", settings.SMTP_PORT)
    print("SMTP_USER:", settings.SMTP_USER)
    print("SMTP_PASS is set:", bool(settings.SMTP_PASS))
    print("FROM_EMAIL:", settings.INVITE_FROM_EMAIL)
    
    email_svc = EmailService(
        smtp_host=settings.SMTP_HOST,
        smtp_port=settings.SMTP_PORT,
        smtp_user=settings.SMTP_USER,
        smtp_pass=settings.SMTP_PASS,
        from_email=settings.INVITE_FROM_EMAIL,
    )
    
    print("Sending test message notification to sabari@axtr.in...")
    res = await email_svc.send_ticket_message_notification(
        to_email="sabari@axtr.in",
        recipient_name="Sabari Test",
        sender_name="⚖️ Lawyer (Test)",
        message_content="This is a test pre-consultation message to verify SMTP settings.",
        ticket_id="193defe7-d54f-46df-9c50-24501574efd4"
    )
    print("Result:", res)

if __name__ == "__main__":
    asyncio.run(test())
