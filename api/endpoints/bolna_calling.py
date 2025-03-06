from datetime import datetime, timedelta
import os
import aiohttp
from fastapi import APIRouter, Depends, HTTPException
import httpx
from fastapi import FastAPI, HTTPException
import pytz
import requests
from pydantic import BaseModel
from api.endpoints.Email_config import send_low_balance_email
from api.models import ProcessedExecution
from api.models.payment_data import UserBalance, check_user_balance
from api.models.user import AI_calling
from auth.auth_bearer import get_current_user
from fastapi import FastAPI, File, UploadFile, HTTPException
import requests
import os
from tempfile import NamedTemporaryFile
from sqlalchemy.orm import Session
from database import get_db
from sqlalchemy.exc import IntegrityError

router = APIRouter()

utc_now = pytz.utc.localize(datetime.utcnow())
ist_now = utc_now.astimezone(pytz.timezone('Asia/Kolkata'))

BOLNA_API_URL = "https://api.bolna.dev/agent/{agent_id}/executions"

@router.get("/api/agent/dashboard_data/")
async def get_agent_executions(
    current_user: AI_calling = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    default_agent_id = current_user.agent_id
    if not default_agent_id:
        raise HTTPException(status_code=400, detail="Agent ID is required but not found")

    api_key = current_user.api_key
    if not api_key:
        raise HTTPException(status_code=500, detail="API key is missing")

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BOLNA_API_URL.format(agent_id=default_agent_id), headers=headers)

        response.raise_for_status()
        result = response.json()
    
    except HTTPException as http_exc:
        raise http_exc
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            raise HTTPException(status_code=400, detail="Bad Request: Invalid agent_id")
        elif e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Not Found: No data found for the given agent_id")
        else:
            raise HTTPException(status_code=e.response.status_code, detail=f"An error occurred: {e.response.text}")
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error.")

    user_balance = db.query(UserBalance).filter(UserBalance.user_id == current_user.user_id).first()
    
    if not user_balance:
        user_balance = UserBalance(user_id=current_user.user_id, balance=0, last_email_sent=ist_now)  
        db.add(user_balance)
        db.commit()
        db.refresh(user_balance)  

        send_low_balance_email(user_email=current_user.user_email, user_name=current_user.user_name, balance=user_balance.balance)

    processed_ids = {p.execution_id for p in db.query(ProcessedExecution).filter_by(user_id=current_user.user_id).all()}

    total_calls = len(result)
    successful_calls = 0
    total_duration_seconds = 0
    total_call_cost = 0
    total_call_cost_with_extra = 0
    total_deduction = 0
    new_executions = []
    data = []
    extra_charge_details = []  

    for r in result:
        execution_id = r.get("id")
        call_status = r.get("status", "").strip().lower()
        
        if call_status == "completed":
            successful_calls += 1

        duration_seconds = float(r.get("telephony_data", {}).get("duration", 0)) if r.get("telephony_data") else 0
        duration_minutes = round(duration_seconds / 60, 2)
        call_cost = r.get("total_cost", 0)
        extra_charge = round(call_cost  * 0.50, 2)  
        call_cost_with_extra = round(call_cost + extra_charge, 2)

        is_new_execution = execution_id not in processed_ids

        if is_new_execution and user_balance.balance >= (total_deduction + call_cost_with_extra):
            total_deduction += call_cost_with_extra
            new_executions.append(ProcessedExecution(user_id=current_user.user_id, execution_id=execution_id))

        total_duration_seconds += duration_seconds
        total_call_cost += call_cost
        total_call_cost_with_extra += call_cost_with_extra

        extra_charge_details.append({
            "execution_id": execution_id,
            "duration_minutes": duration_minutes,
            "call_cost": call_cost,
            "extra_charge": extra_charge,
            "total_cost_with_extra": call_cost_with_extra
        })

        data.append({
            "id": execution_id,
            "agent_id": r.get("agent_id"),
            "batch_id": r.get("batch_id"),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "scheduled_at": r.get("scheduled_at"),
            "answered_by_voice_mail": r.get("answered_by_voice_mail"),
            "conversation_duration": r.get("conversation_duration"),
            "total_cost": r.get("total_cost"),
            "transcript": r.get("transcript"),
            "cost_breakdown": r.get("cost_breakdown", {}),
            "extracted_data": r.get("extracted_data", {}),
            "summary": r.get("summary"),
            "error_message": r.get("error_message"),
            "status": r.get("status"),
            "telephony_data": r.get("telephony_data", {}),
            "transfer_call_data": r.get("transfer_call_data", {}),
            "context_details": r.get("context_details", {}),
            "batch_run_details": r.get("batch_run_details", {}),
            "extra_charge": extra_charge,
            "newly_deducted": is_new_execution  
        })

    if new_executions:
        user_balance.balance -= total_deduction
        db.bulk_save_objects(new_executions)  
        db.commit()
        
    return {
        "total_calls": total_calls,
        "successful_calls": successful_calls,
        "total_duration_minutes": round(total_duration_seconds / 60, 2),
        "total_call_cost": round(total_call_cost, 2),
        "total_call_cost_with_extra_charge": round(total_call_cost_with_extra, 2),
        "updated_balance": round(user_balance.balance, 2) if new_executions else "No balance deducted",
        "available_balance": user_balance.balance,
        "extra_charge_breakdown": extra_charge_details,  
        "executions": data
    }


BOLNA_call_API_URL = "https://api.bolna.dev/call"

@router.post("/make_call")
def make_call(recipient_phone_number: str, db: Session = Depends(get_db), current_user: AI_calling = Depends(get_current_user)):
    try:
        check_user_balance(db, current_user.user_id, required_balance=14)

        agent_id=current_user.agent_id
        BOLNA_API_KEY = current_user.api_key
        from_phone_number = current_user.phone_no

        headers = {
            "Authorization": f"Bearer {BOLNA_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "agent_id": agent_id,
            "recipient_phone_number": f"+91{recipient_phone_number}",
            "from_phone_number": f"+{from_phone_number}"
        }

        response = requests.post(BOLNA_call_API_URL, json=payload, headers=headers)
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        
        return response.json()
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred {str(e)}")


BOLNA_batches_API_URL = "https://api.bolna.dev/batches"

@router.post("/batch_create/")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AI_calling = Depends(get_current_user)
):
    try:
        check_user_balance(db, current_user.user_id, required_balance=14)

        AGENT_ID = current_user.agent_id
        BOLNA_API_KEY = current_user.api_key
        FROM_PHONE = current_user.phone_no
        from_phone_number= f"+{FROM_PHONE}"

        with NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
            temp_file.write(await file.read())
            file_path = temp_file.name

        with open(file_path, "rb") as f:
            headers = {"Authorization": f"Bearer {BOLNA_API_KEY}"}
            files = {"file": (file.filename, f, "text/csv")}
            data = {"agent_id": AGENT_ID, "from_phone_number": from_phone_number}

            response = requests.post(BOLNA_batches_API_URL, headers=headers, files=files, data=data)

        os.remove(file_path)

        return response.json()

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred {str(e)}")
    

@router.get("/batches/all")
def get_all_batches(current_user: AI_calling = Depends(get_current_user)):
    url = f"https://api.bolna.dev/batches/{current_user.agent_id}/all"
    headers = {"Authorization": f"Bearer {current_user.api_key}"}

    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code, 
                detail={"error": "Failed to retrieve batches", "details": response.text}
            )
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail={"error": "Request failed", "details": str(e)})
    


class ScheduleBatchRequest(BaseModel):
    batch_id: str
    scheduled_at: str='2025-02-22T14:30:00'  # Expected format: YYYY-MM-DDTHH:MM:SS "2025-02-22T14:30:00"

@router.post("/batches/schedule/call/")
async def schedule_batch(request: ScheduleBatchRequest, db: Session = Depends(get_db), current_user: AI_calling = Depends(get_current_user)):
    try:
        check_user_balance(db, current_user.user_id, required_balance=14)

        API_KEY = current_user.api_key
        
        if not API_KEY:
            raise HTTPException(status_code=401, detail="Missing API Key")
        
        url_schedule = f"https://api.bolna.dev/batches/{request.batch_id}/schedule"

        # Validate scheduled_at format
        try:
            scheduled_time = datetime.strptime(request.scheduled_at, '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DDTHH:MM:SS.")

        headers = {"Authorization": f"Bearer {API_KEY}"}  # Ensure Bearer prefix

        files = {"scheduled_at": (None, scheduled_time)}

        async with aiohttp.ClientSession() as session:
            async with session.post(url_schedule, headers=headers, data=files) as response:
                response_data = await response.json()

                if response.status != 200:
                    raise HTTPException(status_code=response.status, detail=f"Error scheduling batch: {response_data}")

                return {
                    "status": "success",
                    "data": {
                        "batch_id": request.batch_id,
                        "scheduled_at": request.scheduled_at,
                        "response": response_data
                    }
                }
            
    except HTTPException as http_exc:
        raise http_exc
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=500, detail=f"HTTP Client Error: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred {str(e)}")
    

@router.post("/batches/{batch_id}/stop")
def stop_batch(batch_id: str, current_user: AI_calling = Depends(get_current_user)):
    url = f"https://api.bolna.dev/batches/{batch_id}/stop"
    headers = {"Authorization": f"Bearer {current_user.api_key}"}

    try:
        response = requests.post(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code, 
                detail={"error": f"Failed to stop batch {batch_id}", "details": response.text}
            )
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail={"error": "Request failed", "details": str(e)})
    



    
@router.get("/batches/{batch_id}/executions")
def get_batch_executions(batch_id: str, current_user: AI_calling = Depends(get_current_user)):
    url = f"https://api.bolna.dev/batches/{batch_id}/executions"
    headers = {"Authorization": f"Bearer {current_user.api_key}"}

    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code, 
                detail={"error": f"Failed to retrieve executions for batch {batch_id}", "details": response.text}
            )
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail={"error": "Request failed", "details": str(e)})
    
@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: str, current_user: AI_calling = Depends(get_current_user)):
    url = f"https://api.bolna.dev/batches/{batch_id}"
    headers = {"Authorization": f"Bearer {current_user.api_key}"}

    try:
        response = requests.delete(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code, 
                detail={"error": f"Failed to delete batch {batch_id}", "details": response.text}
            )
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail={"error": "Request failed", "details": str(e)})
    


@router.get("/all_agents_for_admin/")
def get_agents(db: Session = Depends(get_db), current_user: AI_calling = Depends(get_current_user)):
    try:
        BOLNA_API_URL = "https://api.bolna.dev/v2/agent/all"
        headers = {"Authorization": f"Bearer {current_user.api_key}"}

        response = requests.get(BOLNA_API_URL, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)

        result = response.json()

        user_balance = db.query(UserBalance).filter(UserBalance.user_id == current_user.user_id).first()
        if not user_balance:
            raise HTTPException(status_code=404, detail="Balance record not found for the user.")

        all_data = []
        for r in result:
            data = {
                "client_name": current_user.user_name,
                "client_available_balance": user_balance.balance,
                "id": r.get("id"),
                "agent_name": r.get("agent_name"),
                "agent_status": r.get("agent_status"),
                "agent_welcome_message": r.get("agent_welcome_message"),
                "agent_type": r.get("agent_type"),
                "webhook_url": r.get("webhook_url"),
                "tasks": r.get("tasks", {}),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }

            agent_prompts = r.get("agent_prompts_task_1", {})
            if agent_prompts:  
                data["agent_prompts_task_1"] = agent_prompts

            all_data.append(data)

        return all_data

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail={"error": "Request failed", "details": str(e)})
