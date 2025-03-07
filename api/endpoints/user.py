from datetime import datetime, timedelta
import json
import jwt
from fastapi import APIRouter, Depends, HTTPException,Form
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from auth.auth_bearer import JWTBearer, get_admin, get_current_user
from database import get_db, api_response
from ..models.user import  AI_calling
from ..schemas import LoginInput, ChangePassword, UserCreate, UpdateUser, UserType
import bcrypt
import random
import pytz
from sqlalchemy.orm import joinedload
import redis
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter()

user_ops = AI_calling()

redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

def generate_token(data):
    exp = datetime.utcnow() + timedelta(days=1)
    token_payload = {'user_id': data['emp_id'], 'exp': exp}
    token = jwt.encode(token_payload, 'cat_walking_on_the street', algorithm='HS256')
    return token, exp


@router.post('/ai_calling/login/')
async def AI_Interviewers(credential: LoginInput):
    try:
        response = user_ops.AI_calling_login(credential)
        return response
    except HTTPException as e:
        raise
    except Exception as e:
        return HTTPException(status_code=500, detail=f"login failed: {str(e)}")


@router.post("/insert/ai_calling_register_user/")
def AI_calling_register(
            user_name: str = Form(...),
            user_email: str = Form(...),
            user_password: str = Form(...),
            user_type: str = UserType.user,
            phone_no: str = Form(...),
            api_key : str = Form(...),
            agent_id: str = Form(...),
            db: Session = Depends(get_db)):
    try:
        if not AI_calling.validate_email(user_email):
            raise HTTPException(status_code=400, detail="Invalid email format")

        if not AI_calling.validate_password(user_password):
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

        if not AI_calling.validate_phone_number(phone_no):
            raise HTTPException(status_code=400, detail="Phone Number must be  10 digit")
        
        email_db=db.query(AI_calling).filter(AI_calling.user_email==user_email).first()
        if email_db:
            raise HTTPException(status_code=400, detail=f"Email {user_email} already exists")

        utc_now = pytz.utc.localize(datetime.utcnow())
        ist_now = utc_now.astimezone(pytz.timezone('Asia/Kolkata'))

        hashed_password = bcrypt.hashpw(user_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        usr = AI_calling(
            user_name=user_name,
            user_email=user_email,
            user_password=hashed_password,
            user_type=user_type,  
            phone_no=phone_no,
            api_key=api_key,
            agent_id=agent_id,
            created_on=ist_now,
            updated_on=ist_now
        )
        db.add(usr)
        db.commit()

        response = api_response(200, message="User Created successfully")
        return response

    except HTTPException as http_exc:
        raise http_exc

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="A database error occurred while register.")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="An unexpected error occurred  while register.")
        

@router.put("/update_user_type/")
def update_user(
    user_id: int,
    user_type: str = None,
    new_password: str = None,
    phone_no: str = None,
    api_key:str = None,
    agent_id:str = None,
    db: Session = Depends(get_db)
):
    try:
        user = db.query(AI_calling).filter(AI_calling.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if phone_no and not AI_calling.validate_phone_number(phone_no):
            raise HTTPException(status_code=400, detail="Phone number must be 10 digits")

        if new_password and not AI_calling.validate_password(new_password):
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

        if user_type:
            user.user_type = user_type
        if new_password:
            user.user_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        if phone_no:
            user.phone_no = phone_no
        if api_key:
            user.api_key = api_key
        if agent_id:
            user.agent_id = agent_id

        db.commit()
        db.refresh(user)
        return {"message": "User details updated successfully"}
    except HTTPException as e:
        raise e
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred while updating user details.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error occurred while updating user details: {e}")
    
@router.put("/update_password/")
def update_user(
    password: str ,
    new_password: str,
    db: Session = Depends(get_db),
    current_user: AI_calling = Depends(get_current_user), 
):
    try:
        user = db.query(AI_calling).filter(AI_calling.user_id ==current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if password and not AI_calling.validate_password(password):
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

        if new_password and not AI_calling.validate_password(new_password):
            raise HTTPException(status_code=400, detail="new Password must be at least 8 characters long")
        
        if password !=new_password:
            raise HTTPException(status_code=400, detail="Password does not match")
        
        user.user_password=new_password

        db.commit()
        db.refresh(user)
        return {"message": "Password updated successfully"}
    except HTTPException as e:
        raise e
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred while updating Password.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error occurred while updating Password.")


@router.get("/get_my_profile")
def get_current_user_details(
    current_user: AI_calling = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        user_details = {
            "username": current_user.user_name,
            "email": current_user.user_email,
            "user_type": current_user.user_type,
            "phone_no": current_user.phone_no,
        }
        return api_response(data=user_details, status_code=200)
    except Exception:
        raise HTTPException(status_code=500, detail="Unexpected error occurred while retrieving profile.")

@router.get("/get_all_users")
def get_all_users(db: Session = Depends(get_db)):
    try:
        users = db.query(AI_calling).all()
        if not users:
            raise HTTPException(status_code=404, detail="No users found")

        user_list = [
            {
                "user_id": user.user_id,
                "username": user.user_name,
                "email": user.user_email,
               # "user_password": user.user_password,
                "user_type": user.user_type,
                "phone_no": user.phone_no,
            }
            for user in users
        ]
        return api_response(data=user_list, status_code=200)
    except Exception:
        raise HTTPException(status_code=500, detail="Unexpected error occurred while retrieving users.")

@router.delete("/delete/user/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(AI_calling).filter(AI_calling.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        db.delete(user)
        db.commit()
        return {"message": "User deleted successfully"}
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unexpected error occurred while deleting user.")
