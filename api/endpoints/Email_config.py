import os
import smtplib
import logging
from email.mime.text import MIMEText
from dotenv import load_dotenv
from .celery_app import celery_app

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER_NAME")
SMTP_PORT = int(os.getenv("SMTP_PORT_NAME", 465))
SMTP_USERNAME = os.getenv("SMTP_USERNAME_NAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD_NAME")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@celery_app.task(bind=True, autoretry_for=(smtplib.SMTPException,), retry_kwargs={"max_retries": 3})
def send_low_balance_email(self, user_email: str, user_name: str, balance: float):
    """
    Sends an email alert when the user’s balance is low.
    Retries up to 3 times if an SMTP error occurs.
    """
    subject = "⚠️ Low Balance Alert!"

    message = f"""
    <html>
    <body>
        <p>Dear {user_name},</p>
        <p>Your account balance is critically low! Your current balance is <strong>₹{balance}</strong>.</p>
        <p>Please recharge your account immediately to continue using the service.</p>
        <p>🔗 <a href="http://localhost:5173/payment_dashborad">Recharge Now</a></p>
        <p>Best Regards,<br>Your Support Team</p>
    </body>
    </html>
    """

    msg = MIMEText(message, "html")
    msg["Subject"] = subject
    msg["From"] = SMTP_USERNAME
    msg["To"] = user_email

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_USERNAME, user_email, msg.as_string())
        
        logger.info(f"Low balance email sent to {user_email}")
        return "Email sent successfully"
    except smtplib.SMTPAuthenticationError as e:
        logger.error("SMTP Authentication Failed: %s", e)
        return "SMTP Authentication Failed"
    except smtplib.SMTPException as e:
        logger.error("SMTP error: %s", e)
        raise self.retry(exc=e)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        return f"Unexpected error: {e}"
