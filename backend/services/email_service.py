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

    async def send_lawyer_assigned_email(
        self,
        to_email: str,
        user_name: str,
        lawyer_name: str,
        ticket_id: str,
    ) -> bool:
        """
        Notifies the user that a lawyer has accepted their case.
        Sent immediately after a lawyer self-assigns or admin assigns a ticket.

        The email tells the user:
          - Which lawyer has been assigned
          - That they will be contacted to schedule a call
          - What the ticket ID is for reference
        """
        subject = "A lawyer has accepted your case — Digirett"
        html_content = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee;">
            <h2 style="color: #2D3748;">Good news! A lawyer has accepted your case.</h2>
            <p>Hi <strong>{user_name}</strong>,</p>
            <p>
                <strong>{lawyer_name}</strong> has reviewed your case and accepted it.
                They will be in touch to schedule a consultation call.
            </p>
            <div style="background:#f7f7f7; border-left:4px solid #4299e1; padding:12px 16px; margin:24px 0; border-radius:4px;">
                <p style="margin:0; font-size:13px; color:#718096;">Case Reference</p>
                <p style="margin:4px 0 0; font-weight:bold; font-size:15px; color:#2d3748;">{ticket_id[:8].upper()}</p>
            </div>
            <p style="color:#4a5568;">You will receive a booking link shortly to schedule your call.</p>
            <hr style="border:none; border-top:1px solid #eee; margin:30px 0;">
            <p style="font-size:0.8em; color:#A0AEC0;">This is an automated message from the Digirett platform.</p>
        </div>
        """
        return await self._send(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
        )

    async def send_booking_confirmation_email(
        self,
        to_email: str,
        user_name: str,
        meet_link: str,
        start_time: str,
    ) -> bool:
        """
        Sent to the user after Cal.com confirms a booking.
        Contains the Google Meet link and scheduled time.
        """
        subject = "Your consultation is booked — Digirett"
        html_content = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee;">
            <h2 style="color: #2D3748;">Your consultation is confirmed!</h2>
            <p>Hi <strong>{user_name}</strong>,</p>
            <p>Your legal consultation has been scheduled. Here are your details:</p>
            <div style="background:#f7f7f7; border-left:4px solid #48bb78; padding:12px 16px; margin:24px 0; border-radius:4px;">
                <p style="margin:0; font-size:13px; color:#718096;">Scheduled Time</p>
                <p style="margin:4px 0 8px; font-weight:bold; font-size:15px; color:#2d3748;">{start_time}</p>
                <p style="margin:0; font-size:13px; color:#718096;">Google Meet Link</p>
                <p style="margin:4px 0 0;">
                    <a href="{meet_link}" style="color:#3182ce; font-weight:bold;">{meet_link}</a>
                </p>
            </div>
            <p style="color:#4a5568;">
                You will also receive a reminder 15 minutes before the call.
            </p>
            <div style="text-align:center; margin:30px 0;">
                <a href="{meet_link}"
                   style="background-color:#3182ce; color:white; padding:12px 28px;
                          text-decoration:none; border-radius:6px; font-weight:bold;">
                   Join Google Meet
                </a>
            </div>
            <hr style="border:none; border-top:1px solid #eee; margin:30px 0;">
            <p style="font-size:0.8em; color:#A0AEC0;">Digirett Legal Platform</p>
        </div>
        """
        return await self._send(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
        )

    async def send_admin_unassigned_alert(
        self,
        admin_email: str,
        unassigned_tickets: list,
    ) -> bool:
        """
        Sent to the admin every 30 minutes when there are unassigned tickets
        older than 30 minutes.

        unassigned_tickets: list of dicts with keys:
          ticket_id, created_at, user_display_name, user_email
        """
        if not unassigned_tickets:
            return True

        subject = f"⚠️ {len(unassigned_tickets)} unassigned case(s) need attention — Digirett"

        rows = "".join(
            f"""
            <tr>
                <td style="padding:8px 12px; border-bottom:1px solid #eee;">{t.get('ticket_id', '')[:8].upper()}</td>
                <td style="padding:8px 12px; border-bottom:1px solid #eee;">{t.get('user_display_name') or 'N/A'}</td>
                <td style="padding:8px 12px; border-bottom:1px solid #eee;">{t.get('user_email') or 'N/A'}</td>
                <td style="padding:8px 12px; border-bottom:1px solid #eee;">{t.get('created_at', '')[:16].replace('T', ' ')}</td>
            </tr>
            """
            for t in unassigned_tickets
        )

        html_content = f"""
        <div style="font-family: sans-serif; max-width: 700px; margin: auto; padding: 20px; border: 1px solid #eee;">
            <h2 style="color: #c53030;">⚠️ Unassigned Cases Alert</h2>
            <p>The following {len(unassigned_tickets)} case(s) have been waiting for a lawyer for more than 30 minutes:</p>
            <table style="width:100%; border-collapse:collapse; margin:16px 0;">
                <thead>
                    <tr style="background:#f7f7f7; text-align:left;">
                        <th style="padding:8px 12px;">Ticket ID</th>
                        <th style="padding:8px 12px;">User</th>
                        <th style="padding:8px 12px;">Email</th>
                        <th style="padding:8px 12px;">Created At</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
            <p style="color:#4a5568;">Please log in to the admin dashboard to assign these cases.</p>
            <hr style="border:none; border-top:1px solid #eee; margin:30px 0;">
            <p style="font-size:0.8em; color:#A0AEC0;">Digirett Admin Alert — automated notification</p>
        </div>
        """
        return await self._send(
            to_email=admin_email,
            subject=subject,
            html_content=html_content,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INTERNAL — shared SMTP sender
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _send(self, to_email: str, subject: str, html_content: str) -> bool:
        """Shared SMTP send helper used by all email methods."""
        if not self._smtp_pass:
            logger.error("❌ Cannot send email: SMTP_PASS is not configured.")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from_email
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
            logger.info(f"📧 Email sent | to={to_email} | subject={subject[:60]}")
            return True
        except Exception as exc:
            logger.error(f"❌ Failed to send email to {to_email} | {exc}", exc_info=True)
            return False
