import logging
import resend
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)

class EmailService:
    """
    EmailService — handles sending invitation and notification emails via Resend.
    """

    def __init__(self, api_key: str, from_email: str) -> None:
        if not api_key:
            logger.warning("⚠️ RESEND_API_KEY is not set. Email notifications will be disabled.")
        
        resend.api_key = api_key
        self._from_email = from_email
        logger.info("✅ EmailService initialized")

    def send_invitation_email(
        self, 
        to_email: str, 
        role: str, 
        invite_token: str
    ) -> bool:
        """
        Sends a custom invitation email to a new Lawyer or Admin.
        
        The email contains a link to the frontend invitation landing page.
        """
        if not resend.api_key:
            logger.error("❌ Cannot send email: RESEND_API_KEY is missing.")
            return False

        # Build the invitation link from settings so it works in both dev and prod
        invite_link = f"{settings.FRONTEND_URL}/invite?token={invite_token}"
        
        subject = f"Invitation to join Digirett as a {role.capitalize()}"
        
        html_content = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee;">
            <h2 style="color: #2D3748;">Welcome to Digirett</h2>
            <p>You have been invited to join the Digirett AI RAG Chatbot platform as a <strong>{role.capitalize()}</strong>.</p>
            <p>Please click the button below to complete your registration and set up your account:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{invite_link}" 
                   style="background-color: #4A5568; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                   Accept Invitation
                </a>
            </div>
            <p style="font-size: 0.9em; color: #718096;">
                If the button doesn't work, copy and paste this link into your browser:<br>
                <a href="{invite_link}">{invite_link}</a>
            </p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
            <p style="font-size: 0.8em; color: #A0AEC0;">
                This invitation was sent by the Digirett Admin Team.
            </p>
        </div>
        """

        try:
            params = {
                "from": self._from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }
            
            response = resend.Emails.send(params)
            logger.info(f"📧 Invitation email sent | to={to_email} | role={role} | id={response.get('id')}")
            return True
            
        except Exception as exc:
            logger.error(f"❌ Failed to send invitation email to {to_email} | {exc}", exc_info=True)
            return False
