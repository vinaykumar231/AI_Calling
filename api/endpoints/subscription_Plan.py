from datetime import datetime, timedelta
import os
from typing import List, Optional
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException,BackgroundTasks, Query
import pytz
import redis
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from api.endpoints import celery_app
from api.models.user import AI_calling
from auth.auth_bearer import get_current_user
from database import get_db
from ..models.payment_data import PaymentHistory, SubscriptionPlan, UserBalance, UserSubscription
from sqlalchemy.orm import joinedload
from ..schemas import SubscriptionPlanCreate, UpdateSubscriptionBooleans, SubscribeRequest
from .Email_config import send_low_balance_email
from sqlalchemy.exc import SQLAlchemyError



router = APIRouter()
load_dotenv()

@router.post("/create_subscription_plan/")
def create_subscription_plan(request: SubscriptionPlanCreate, db: Session = Depends(get_db)):
    try:
        existing_plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == request.name).first()
        if existing_plan:
            raise HTTPException(status_code=400, detail="Subscription plan with this name already exists")

        new_plan = SubscriptionPlan(
            name=request.name,
            price=request.price,
            calling_seconds=request.calling_seconds,
            languages=request.languages,
            is_popular=request.is_popular,
            is_recommended=request.is_recommended,
            is_custom=request.is_custom
        )

        db.add(new_plan)
        db.commit()
        db.refresh(new_plan)

        return {"status": "success", "message": "Subscription plan created successfully", "plan": new_plan}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Integrity error, possibly duplicate name")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    
@router.get("/subscription-plans", response_model=None)
def get_subscription_plans(db: Session = Depends(get_db)):
    try:
        plans = db.query(SubscriptionPlan).all()  # Fetch all subscription plans
        return plans
    except HTTPException as http_exc:
        raise http_exc
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail="A database error occurred while fetching data.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="An unexpected error occurred while fetching data.")

@router.put("/update_subscription_plan/{plan_id}/")
def update_subscription_booleans(
    plan_id: int, 
    request: UpdateSubscriptionBooleans, 
    db: Session = Depends(get_db)
):
    try:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()

        if not plan:
            raise HTTPException(status_code=404, detail="Subscription plan not found")

        plan.is_popular = request.is_popular
        plan.is_recommended = request.is_recommended
        plan.is_custom = request.is_custom

        db.commit()
        db.refresh(plan)

        return {"status": "success", "message": "Subscription plan updated successfully", "plan": plan}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Integrity error while updating subscription plan")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.delete("/subscription-plans/{plan_id}", response_model=None)
def delete_subscription_plan(plan_id: int, db: Session = Depends(get_db)):
    try:
        plan_to_delete = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()

        if not plan_to_delete:
            raise HTTPException(status_code=404, detail="Subscription Plan not found")

        db.delete(plan_to_delete)
        db.commit()  

        return {"detail": "Subscription Plan deleted successfully"}  
    except HTTPException as http_exc:
        raise http_exc
    except SQLAlchemyError as e:
        db.rollback()  
        raise HTTPException(status_code=404, detail="A database error occurred while deleting data.")
    except Exception as e:
        db.rollback()  
        raise HTTPException(status_code=500, detail="An unexpected error occurred while deleting data.")



@router.post("/subscribe/")
def subscribe_to_plan(
    request: SubscribeRequest, 
    db: Session = Depends(get_db), 
    current_user: AI_calling = Depends(get_current_user)
):
    try:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == request.plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail="Subscription plan not found")

        active_subscription = db.query(UserSubscription).filter(UserSubscription.user_id == current_user.user_id).first()

        if  not active_subscription:
            raise HTTPException(status_code=400, detail="User not found")
        
        # Fetch user subscription and corresponding plan
        user_sub = db.query(UserSubscription).filter(UserSubscription.user_id == current_user.user_id, UserSubscription.is_active == True).first()

        if user_sub:
            subscription_plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == user_sub.plan_id).first()

        start_date = datetime.utcnow()
        expiry_date = start_date + timedelta(days=request.duration_days)

        new_subscription = UserSubscription(
            user_id=current_user.user_id,
            plan_id=request.plan_id,
            start_date=start_date,
            expiry_date=expiry_date,
            is_active=True
        )

        db.add(new_subscription)
        db.commit()
        db.refresh(new_subscription)

        return {"status": "success", "message": "Subscription activated", "subscription": new_subscription}
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error.")



@router.get("/user/subscription/")
def get_user_subscription(db: Session = Depends(get_db), current_user: AI_calling = Depends(get_current_user)):

    subscription = db.query(UserSubscription).options(joinedload(UserSubscription.subscription_plan)).filter(UserSubscription.user_id == current_user.user_id,UserSubscription.is_active == True).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")

    return {
        "status": "success",
        "subscription": {
            "plan_id": subscription.plan_id,
            "subscription_plan": subscription.subscription_plan.name,
            "start_date": subscription.start_date,
            "expiry_date": subscription.expiry_date,
            "is_active": subscription.is_active

        }
    }


#redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
EMAIL_RATE_LIMIT_HOURS = 24  # Cooldown period before sending again

@router.get("/user/user_balance/")
def user_balance(db: Session = Depends(get_db), current_user:AI_calling=Depends(get_current_user)):
    try:
        user_balance = (
            db.query(UserBalance)
            .options(joinedload(UserBalance.users))
            .filter(UserBalance.user_id == current_user.user_id)
            .first()
        )

        if not user_balance:
            raise HTTPException(status_code=404, detail="Balance record not found for the user.")

        user_name = user_balance.users.user_name if user_balance.users else "Unknown"
        user_email = user_balance.users.user_email if user_balance.users else None
        balance = user_balance.balance

        if balance is None:
            raise HTTPException(status_code=400, detail="Invalid balance data.")

        if balance < 14:
            if not user_email:
                raise HTTPException(status_code=400, detail="User email not found.")

            current_time = datetime.utcnow()

            if user_balance.last_email_sent:
                time_since_last_email = (current_time - user_balance.last_email_sent).total_seconds()
                
                if time_since_last_email < EMAIL_RATE_LIMIT_HOURS * 3600:
                    remaining_time = int((EMAIL_RATE_LIMIT_HOURS * 3600) - time_since_last_email)
                    remaining_hours = remaining_time // 3600
                    remaining_minutes = (remaining_time % 3600) // 60
                    return {
                        "status": "success",
                        "message": f"Email already sent recently. Please wait {remaining_hours} hours {remaining_minutes} minutes before sending again.",
                        "user_name": user_name,
                        "balance": balance
                    }

            send_low_balance_email(user_email, user_name, balance)
            user_balance.last_email_sent = current_time
            db.commit()

            return {
                "status": "success",
                "message": "Low balance email sent successfully",
                "user_name": user_name,
                "balance": balance
            }
        else:
            return {
                "status": "success",
                "message": "Balance is sufficient, no email sent",
                "user_name": user_name,
                "balance": balance
            }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
    
@router.get("/payment_history/", response_model=List[dict])
async def get_payment_history(
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    transaction_type: Optional[str] = Query(None, description="Filter by transaction type (Deposit/Deduction)"),
    limit: int = Query(10, description="Number of records to fetch"),
    offset: int = Query(0, description="Pagination offset"),
    db: Session = Depends(get_db)
):
    try:
        query = db.query(PaymentHistory).options(joinedload(PaymentHistory.users))

        if user_id:
            query = query.filter(PaymentHistory.user_id == user_id)

        if transaction_type:
            query = query.filter(PaymentHistory.transaction_type == transaction_type)

        payments = query.order_by(PaymentHistory.timestamp.desc()).offset(offset).limit(limit).all()

        if not payments:
            raise HTTPException(status_code=404, detail="No payment history found")

        return [
            {
                "id": p.id,
                "user_id": p.user_id,
                "user_name": p.users.user_name,
                "transaction_type": p.transaction_type,
                "amount": p.amount,
                "timestamp": p.timestamp,
                "description": p.description
            }
            for p in payments
        ]
    except HTTPException as http_exc:
        raise http_exc
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail="A database error occurred while update Lease Sale.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="An unexpected error occurred while update Lease Sale.")