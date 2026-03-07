import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
import aiosmtplib
import logging

logger = logging.getLogger(__name__)

class EmailService:
    @staticmethod
    async def _send_email(to_email: str, subject: str, html_content: str):
        """Internal helper to send email asynchronously using aiosmtplib."""
        if not all([settings.SMTP_USER, settings.SMTP_PASSWORD]):
            logger.warning(f"SMTP credentials not configured. Skipping email to {to_email}")
            return

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
        message["To"] = to_email

        html_part = MIMEText(html_content, "html")
        message.attach(html_part)

        try:
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_SERVER,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                start_tls=True if settings.SMTP_PORT == 587 else False,
                use_tls=True if settings.SMTP_PORT == 465 else False,
            )
            logger.info(f"Email sent successfully to {to_email}")
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")

    @staticmethod
    async def send_login_alert(to_email: str, user_name: str, device: str, ip: str, location: str):
        """Sends a security alert email for a new sign-in."""
        subject = "Security Alert: New Sign-in to MediMind AI"
        
        html_content = f"""
        <html>
        <body style="font-family: 'Poppins', sans-serif; color: #0F172A; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; rounded: 16px;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #0D9488; margin-bottom: 0;">MediMind AI</h1>
                    <p style="color: #64748b; margin-top: 5px;">Security Notification</p>
                </div>
                
                <p>Hello <strong>{user_name}</strong>,</p>
                
                <p>Your MediMind AI account was recently signed into from a new device.</p>
                
                <div style="background-color: #f8fafc; padding: 20px; border-radius: 12px; margin: 25px 0;">
                    <p style="margin: 0; font-size: 14px; color: #64748b;">Sign-in Details:</p>
                    <table style="width: 100%; margin-top: 10px;">
                        <tr><td style="padding: 5px 0; font-weight: 600;">Device:</td><td>{device}</td></tr>
                        <tr><td style="padding: 5px 0; font-weight: 600;">Location:</td><td>{location}</td></tr>
                        <tr><td style="padding: 5px 0; font-weight: 600;">IP Address:</td><td>{ip}</td></tr>
                    </table>
                </div>
                
                <p>If this was you, you can safely ignore this email.</p>
                <p style="color: #dc2626; font-weight: 600;">If this wasn't you, please change your password immediately and revoke any suspicious sessions from your security settings.</p>
                
                <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #94a3b8;">
                    <p>© 2026 MediMind AI. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        await EmailService._send_email(to_email, subject, html_content)

    @staticmethod
    async def send_appointment_confirmation(
        to_email: str, 
        user_name: str, 
        doctor_name: str, 
        date: str, 
        time: str, 
        room_url: str,
        is_doctor: bool = False
    ):
        """Sends an appointment confirmation email to either patient or doctor."""
        subject = "Appointment Confirmed: MediMind AI Consultation"
        role_text = "patient" if not is_doctor else "doctor"
        other_party = f"Dr. {doctor_name}" if not is_doctor else f"Patient {user_name}"
        
        html_content = f"""
        <html>
        <body style="font-family: 'Poppins', sans-serif; color: #0F172A; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 16px;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #0D9488; margin-bottom: 0;">MediMind AI</h1>
                    <p style="color: #64748b; margin-top: 5px;">Appointment Confirmation</p>
                </div>
                
                <p>Hello <strong>{user_name if not is_doctor else f"Dr. {doctor_name}"}</strong>,</p>
                
                <p>Your consultation has been successfully scheduled.</p>
                
                <div style="background-color: #f0fdfa; padding: 25px; border-radius: 12px; border-left: 4px solid #0D9488; margin: 25px 0;">
                    <h3 style="margin-top: 0; color: #0D9488;">Consultation Details</h3>
                    <table style="width: 100%;">
                        <tr><td style="padding: 5px 0; font-weight: 600; width: 35%;">With:</td><td>{other_party}</td></tr>
                        <tr><td style="padding: 5px 0; font-weight: 600;">Date:</td><td>{date}</td></tr>
                        <tr><td style="padding: 5px 0; font-weight: 600;">Time:</td><td>{time}</td></tr>
                    </table>
                </div>
                
                <p>You can join the video consultation at the scheduled time using the link below:</p>
                
                <div style="text-align: center; margin: 35px 0;">
                    <a href="{room_url}" style="background-color: #0D9488; color: white; padding: 14px 28px; text-decoration: none; border-radius: 12px; font-weight: 600; box-shadow: 0 4px 10px rgba(13, 148, 136, 0.2);">Join Meeting Room</a>
                </div>
                
                <p style="font-size: 14px; color: #64748b;">If the button doesn't work, copy and paste this URL into your browser:<br>
                <span style="color: #0D9488;">{room_url}</span></p>
                
                <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #94a3b8;">
                    <p>© 2026 MediMind AI. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        await EmailService._send_email(to_email, subject, html_content)

email_service = EmailService()
