import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Celery Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "tasks",
    broker=REDIS_URL,  # Redis as message broker
    backend=REDIS_URL  # Redis as result backend
)

# Celery Configuration
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=False,  # Set False for IST timezone handling
    beat_schedule_filename="celerybeat-schedule",
)

# **Celery Beat Schedule Configuration**
celery_app.conf.beat_schedule = {
    "check-low-balance-every-2-minutes": {
        "task": "tasks.check_and_send_low_balance_emails",  # ✅ FIXED Import Path
        "schedule": crontab(minute="*/2"),  # Runs every 2 minutes
    }
}

