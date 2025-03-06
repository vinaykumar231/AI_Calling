from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
from fastapi import HTTPException
from sqlalchemy.orm import Session

class UserBalance(Base):
    __tablename__ = "user_balance_tb"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    balance = Column(Float, default=0.0)
    last_email_sent = Column(DateTime, nullable=True, default=None)

    users = relationship("AI_calling", back_populates="user_balance")

   
class SubscriptionPlan(Base):
    __tablename__ = "subscription_plan"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    price = Column(Float, nullable=False)
    calling_seconds = Column(Integer, nullable=False)
    languages = Column(String(255), nullable=False)
    is_popular = Column(Boolean, default=False)
    is_recommended = Column(Boolean, default=False)
    is_custom = Column(Boolean, default=False)

    user_subscriptions = relationship("UserSubscription", back_populates="subscription_plan")

class UserSubscription(Base):
    __tablename__ = "user_subscription"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plan.id"))
    start_date = Column(DateTime, default=datetime.utcnow)
    expiry_date = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)


    subscription_plan = relationship("SubscriptionPlan", back_populates="user_subscriptions")
    users = relationship("AI_calling", back_populates="user_subscriptions")
    

class PaymentTransaction(Base):
    __tablename__ = "payment_transaction"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(255), default="INR")
    razorpay_payment_id = Column(String(255),   default=None ,nullable=True)  # Make it nullable
    razorpay_order_id = Column(String(255), unique=True, nullable=False)
    status = Column(String(255), nullable=False, default="Pending")
    created_at = Column(DateTime, default=datetime.utcnow)

class PaymentHistory(Base):
    __tablename__ = "payment_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    transaction_type = Column(String(50), nullable=True)  # "Deposit" or "Deduction"
    amount = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    description = Column(String(255), nullable=True)

    users = relationship("AI_calling", back_populates="payment_history")
    


##################################################################################################

def check_user_balance(db: Session, user_id: int, required_balance: float):
    try:
  
        user_balance = db.query(UserBalance).filter(UserBalance.user_id == user_id).first()

        if not user_balance:
            raise HTTPException(status_code=404, detail="User balance record not found")

        if user_balance.balance < required_balance:
            raise HTTPException(status_code=400, detail=f"Insufficient balance. Please add funds for at least a 1-minute phone call.")
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred {str(e)}")
