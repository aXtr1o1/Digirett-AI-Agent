import logging
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    EmailService — handles sending invitation and notification emails via SMTP.
    Uses aiosmtplib for async STARTTLS sending (compatible with Resend SMTP relay,
    Gmail, Postfix, etc.).
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_pass: str,
        from_email: str,
    ) -> None:
        if not smtp_pass:
            logger.warning("⚠️ SMTP_PASS is not set. Email notifications may fail.")

        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_pass = smtp_pass
        self._from_email = from_email
        logger.info(
            f"✅ EmailService initialized | host={smtp_host}:{smtp_port} | from={from_email}"
        )

    async def send_invitation_email(
        self,
        to_email: str,
        role: str,
        invite_token: str,
        admin_email: Optional[str] = None,
    ) -> bool:
        """
        Sends a custom invitation email to a new Lawyer or Admin via SMTP.

        The email contains a link to the frontend invitation landing page.
        Returns True on success, False on failure.
        """
        if not self._smtp_pass:
            logger.error("❌ Cannot send email: SMTP_PASS is not configured.")
            return False

        # Build invitation link
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

        # Build MIME message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = admin_email if admin_email else self._from_email
        msg["To"] = to_email
        msg.attach(MIMEText(html_content, "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=self._smtp_host,
                port=self._smtp_port,
                username=self._smtp_user,
                password=self._smtp_pass,
                start_tls=True,
            )
            logger.info(f"📧 Invitation email sent | to={to_email} | role={role}")
            return True

        except Exception as exc:
            logger.error(
                f"❌ Failed to send invitation email to {to_email} | {exc}",
                exc_info=True,
            )
            return False
