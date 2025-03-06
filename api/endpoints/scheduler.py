from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from ..models.payment_data import  UserBalance
from ..models.user import AI_calling
from .Email_config import send_low_balance_email  # Import your email function
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def check_and_send_low_balance_emails():
    db: Session = SessionLocal()
    try:
        users = db.query(UserBalance).join(AI_calling).all()

        for user_balance in users:
            user = user_balance.users 
            if user_balance.balance < 14 and user:
                try:
                    result = send_low_balance_email(user.user_email, user.user_name, user_balance.balance)
                    if result:
                        logger.info(f"✅ Email sent to {user.user_email} (Balance: {user_balance.balance})")
                    else:
                        logger.warning(f"⚠️ Failed to send email to {user.user_email}")
                except Exception as e:
                    logger.error(f"❌ Error sending email: {e}")

    except Exception as e:
        logger.error(f"❌ Scheduler error: {e}")

    finally:
        db.close()


# Schedule to run every 1 hour
scheduler.add_job(check_and_send_low_balance_emails, "interval", minutes=1)
scheduler.start()
