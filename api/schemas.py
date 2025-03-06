from pydantic import BaseModel,  Field, EmailStr, validator
from typing import Optional, List
from fastapi import UploadFile, File
from datetime import date, datetime
from enum import Enum
from sqlalchemy import JSON
import re


######################################## User logiin and register #############################
class LoginInput(BaseModel):
    email: str
    user_password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str

    class Config:
        from_attributes = True


class UserType(str, Enum):
    admin = "admin"
    user = "user"
   
   


class UserCreate(BaseModel):
    user_name: str
    user_email: str
    user_password: str
    user_type: UserType = UserType.user
    phone_no: str
    company_name: Optional[str] = None
    industry:  Optional[str] = None

    class Config:
        from_attributes = True


class UpdateUser(BaseModel):
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    phone_no: Optional[int] = None
    user_type: Optional[str] = None
    current_password: Optional[str] = None


##################### Razorpay ########################

class CreateOrderRequest(BaseModel):
    amount: float
    currency: str = "INR"
    receipt: str

class VerifyPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str

######################################## subscription ###################

class SubscriptionPlanCreate(BaseModel):
    name: str
    price: float
    calling_seconds: int
    languages: str
    is_popular: bool = False
    is_recommended: bool = False
    is_custom: bool = False

class UpdateSubscriptionBooleans(BaseModel):
    is_popular: bool
    is_recommended: bool
    is_custom: bool


class SubscribeRequest(BaseModel):
    plan_id: int
    duration_days: int  


