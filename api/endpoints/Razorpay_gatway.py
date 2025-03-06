from datetime import datetime
import os
import razorpay
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import requests
import httpx
from fastapi import FastAPI, APIRouter, HTTPException, Request
import httpx
import hmac
import hashlib
from pydantic import BaseModel
import hmac
import hashlib
import json
from sqlalchemy.orm import Session
import razorpay
from api.models.payment_data import PaymentHistory, PaymentTransaction, UserBalance
from api.models.user import AI_calling
from auth.auth_bearer import get_current_user
from database import get_db
from ..schemas import CreateOrderRequest, VerifyPaymentRequest, VerifyPaymentRequest
from sqlalchemy.exc import SQLAlchemyError
import logging
from sqlalchemy.orm import joinedload


router = APIRouter()
logger = logging.getLogger(__name__)


RAZORPAY_KEY = os.getenv("RAZORPAY_KEYS")
RAZORPAY_SECRET = os.getenv("RAZORPAY_SECRETS")
client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))

if not RAZORPAY_KEY or not RAZORPAY_SECRET:
    raise ValueError("RAZORPAY_KEY or RAZORPAY_SECRET is missing in environment variables.")


@router.post("/create_order/")
async def create_order(request: CreateOrderRequest, db: Session = Depends(get_db), current_user: AI_calling = Depends(get_current_user)):
    try:
        BASE_URL = "https://api.razorpay.com/v1/orders"

        order_data = {
            "amount": int(request.amount * 100),  
            "currency": request.currency,
            "receipt": request.receipt,
        }
        
        order = client.order.create(data=order_data)
    
        payment_transaction = PaymentTransaction(
            user_id=current_user.user_id,
            amount=request.amount,
            currency=request.currency,
            razorpay_order_id=order["id"],
            status="Created",
            created_at=datetime.utcnow()
        )
        db.add(payment_transaction)
        db.commit()
        
        return {
            "status": "success",
            "order_id": order["id"],
            "order_details": order,
        }
    except HTTPException as http_exc:
        raise http_exc
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=f"A database error occurred while create order.{e}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred  while create order.{e}")



def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        })
        return True
    except razorpay.errors.SignatureVerificationError:
        return False

@router.post("/verify_payment/")
async def verify_payment(
    request: VerifyPaymentRequest, 
    db: Session = Depends(get_db), 
    current_user: AI_calling = Depends(get_current_user)
):
    try:
        razorpay_payment_id: str = request.razorpay_payment_id
        razorpay_order_id: str = request.razorpay_order_id
        razorpay_signature: str = request.razorpay_signature

        if not verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
            raise HTTPException(status_code=400, detail="Invalid Razorpay signature")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://api.razorpay.com/v1/payments/{razorpay_payment_id}",auth=(RAZORPAY_KEY, RAZORPAY_SECRET))

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch payment details from Razorpay")

        payment = response.json()
        payment_status = payment.get("status", "failed")  
        payment_amount = payment.get("amount", 0) / 100  
        payment_currency = payment.get("currency", "INR")

        if not current_user.user_id:
            raise HTTPException(status_code=400, detail="User not found")

        transaction = db.query(PaymentTransaction).filter(PaymentTransaction.razorpay_order_id == razorpay_order_id).first()

        if transaction:
            transaction.amount = payment_amount
            transaction.currency = payment_currency
            transaction.razorpay_payment_id = razorpay_payment_id
            transaction.status = payment_status
        else:
            transaction = PaymentTransaction(
                user_id=current_user.user_id,
                amount=payment_amount,
                currency=payment_currency,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_order_id=razorpay_order_id,
                status=payment_status
            )
            db.add(transaction)

        db.commit()
        db.refresh(transaction)  

        payment_history = PaymentHistory(
                user_id=current_user.user_id,
                transaction_type="Deposit",
                amount=payment_amount,
                description=f"Payment received via Razorpay. Order ID: {razorpay_order_id}"
            )
        db.add(payment_history)

        db.commit()

        if payment_status == "captured":
            user_balance = db.query(UserBalance).filter(UserBalance.user_id == current_user.user_id).first()

            if user_balance:
                user_balance.balance += payment_amount
            else:
                user_balance = UserBalance(user_id=current_user.user_id, balance=payment_amount)
                db.add(user_balance)

            db.commit()  

        return {
            "status": "success",
            "message": "Payment verified and processed successfully",
            "payment_details": payment
        }

    except httpx.RequestError as e:
        db.rollback()
        logger.error(f"Razorpay API connection error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to connect to Razorpay API")

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error while processing payment: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error while processing payment")

    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error occurred")
    
    
@router.get("/fetch_payment/")
async def fetch_payments(db: Session = Depends(get_db)):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.razorpay.com/v1/payments",
                auth=(RAZORPAY_KEY, RAZORPAY_SECRET)
            )
        
        if response.status_code == 200:
            payment_data = response.json()
            updated = False
            
            for payment in payment_data.get("items", []):
                transaction = db.query(PaymentTransaction).filter_by(razorpay_payment_id=payment["id"]).first()

                if transaction and transaction.status != payment["status"]:
                    transaction.status = payment["status"]
                    updated = True

                    if payment["status"] == "captured":
                        user_balance = db.query(UserBalance).filter_by(user_id=transaction.user_id).first()
                        if user_balance:
                            user_balance.balance += payment["amount"] / 100  
                        else:
                            db.add(UserBalance(user_id=transaction.user_id, balance=payment["amount"] / 100))
            
            if updated:
                db.commit()  

            return {"status": "success", "payment_details": payment_data}

        raise HTTPException(status_code=response.status_code, detail=f"Failed to fetch payments: {response.text}")

    except httpx.RequestError as e:
        logger.error(f"Error connecting to Razorpay: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error connecting to Razorpay: {str(e)}")
    
    except SQLAlchemyError:
        db.rollback()
        logger.error("Database error while fetching payments", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error while fetching payments.")

    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error while fetching payments: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

    
    
@router.get("/payment-methods")
async def get_payment_methods():
    try:
        order_data = {
            'amount': 100,  
            'currency': 'INR',
            'receipt': 'test_receipt',
            'payment_capture': 1
        }
        
        order = client.order.create(order_data)
        
        return {
            "order_id": order['id'],
            "supported_methods": {
                "card": {
                    "types": ["credit", "debit"],
                    "supported_networks": ["Visa", "MasterCard", "RuPay"]
                },
                "upi": {
                    "types": ["collect", "intent"]
                },
                "netbanking": True,
                "wallet": True,
                "emi": True
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/payment/{payment_id}")
async def get_payment_details(payment_id: str):
    try:
        payment = client.payment.fetch(payment_id)
        
        return {
            "id": payment['id'],
            "amount": payment['amount'] / 100,  
            "status": payment['status'],
            "method": payment['method'],
            "order_id": payment.get('order_id'),
            "created_at": payment['created_at'],
            "currency": payment['currency']
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/payments")
async def list_payments(count: int = 10):
    try:
        payments = client.payment.all({
            'count': count
        })
        
        return {
            "count": len(payments['items']),
            "payments": [{
                "id": p['id'],
                "amount": p['amount'] / 100,
                "status": p['status'],
                "method": p.get('method'),
                "created_at": p['created_at']
            } for p in payments['items']]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.get("/payment_details/{order_id}")
async def fetch_payment_details(order_id: str):
    try:
        order_details = client.order.fetch(order_id)

        if 'payments' not in order_details or len(order_details['payments']) == 0:
            if order_details.get('status') == 'created':
                return {
                    "status": "pending",
                    "message": "No payment has been made yet for this order"
                }
            else:
                raise HTTPException(status_code=404, detail="No payments found for this order")
        
        payment_id = order_details['payments'][0]['id']
        status = order_details.get('status')

        return {
            "payment_id": payment_id,
            "status": status
        }
    except razorpay.errors.RazorpayError as e:
        raise HTTPException(status_code=500, detail=f"Error fetching payment details: {str(e)}")
    





async def fetch_order_status(order_id: str):
    try:
        BASE_URL = "https://api.razorpay.com/v1/orders"

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/{order_id}",auth=(RAZORPAY_KEY, RAZORPAY_SECRET))
        
        if response.status_code == 200:
            order_details = response.json()
            status = order_details.get('status')

            if status == "created":
                return {"status": "created", "message": "Payment has not been initiated yet"}
            elif status == "paid":
                return {"status": "paid", "message": "Payment has been completed successfully"}
            else:
                return {"status": status, "message": "Unknown order status"}
        
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch order details: {response.text}"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching order details: {str(e)}")

@router.get("/verify_order123/{order_id}")
async def verify_order_status123(order_id: str):
    return await fetch_order_status(order_id)


@router.post("/api/razorpay-webhook")
async def handle_webhook(request: Request):
    try:
        raw_body = await request.body()
        payload = await request.json()

        return {"status": "success", "message": "Webhook received"}

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        print(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Error handling webhook")
