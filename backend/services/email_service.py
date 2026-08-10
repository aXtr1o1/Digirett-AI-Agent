"""
services/email_service.py — Email Notification Service with Jinja2 Templating & SMTP Retry Policy
"""

import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates",
    "email",
)


class EmailService:
    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_pass: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> None:
        self._smtp_host = smtp_host or getattr(settings, "SMTP_HOST", "smtp.resend.com")
        self._smtp_port = smtp_port or getattr(settings, "SMTP_PORT", 587)
        self._smtp_user = smtp_user or getattr(settings, "SMTP_USER", "")
        self._smtp_pass = smtp_pass or getattr(settings, "SMTP_PASS", "")
        self._from_email = from_email or getattr(settings, "INVITE_FROM_EMAIL", "sabari@axtr.in")

        if os.path.exists(_TEMPLATES_DIR):
            self._jinja_env = Environment(
                loader=FileSystemLoader(_TEMPLATES_DIR),
                autoescape=select_autoescape(["html", "xml"]),
            )
        else:
            self._jinja_env = None

        logger.info(f"[OK] EmailService initialized | host={smtp_host}:{smtp_port} | from={from_email}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=3), reraise=True)
    async def _send_smtp_message(self, msg: MIMEMultipart) -> None:
        await aiosmtplib.send(
            msg,
            hostname=self._smtp_host,
            port=self._smtp_port,
            username=self._smtp_user,
            password=self._smtp_pass,
            start_tls=True,
        )

    async def send_invitation_email(
        self,
        to_email: str,
        role: str,
        invite_token: str,
        admin_email: Optional[str] = None,
    ) -> bool:
        if not self._smtp_pass:
            logger.error("[ERROR] Cannot send email: SMTP_PASS is not configured.")
            return False

        invite_link = f"{settings.FRONTEND_URL}/invite?token={invite_token}"
        subject = f"Invitation to join Digirett as a {role.capitalize()}"

        if self._jinja_env:
            try:
                template = self._jinja_env.get_template("invitation.html")
                html_content = template.render(role=role, invite_link=invite_link)
            except Exception as exc:
                logger.warning(f"⚠️ Jinja2 template render failed ({exc}) — using fallback HTML")
                html_content = f"<h2>Welcome to Digirett</h2><p>Accept invitation: {invite_link}</p>"
        else:
            html_content = f"<h2>Welcome to Digirett</h2><p>Accept invitation: {invite_link}</p>"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = admin_email if admin_email else self._from_email
        msg["To"] = to_email
        msg.attach(MIMEText(html_content, "html"))

        try:
            await self._send_smtp_message(msg)
            logger.info(f"📧 Invitation email sent | to={to_email} | role={role}")
            return True
        except Exception as exc:
            logger.error(f"❌ Failed to send invitation email | {exc}", exc_info=True)
            return False
