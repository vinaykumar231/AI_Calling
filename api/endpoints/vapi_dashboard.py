import os
import httpx
from fastapi import APIRouter, FastAPI, HTTPException
import logging
from datetime import datetime

router = APIRouter()

url_base = "https://api.vapi.ai/call"  

vapi_api_key=os.getenv("VAPI_API_KEY")
headers = {
    'Authorization': f"Bearer {vapi_api_key}",  
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USD_TO_INR = 85.56 

@router.get("/Vapi_dashboard_data")
async def vapi_dashboard_data():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url=url_base, headers=headers)
            if response.status_code == 200:
                try:
                    response_data = response.json()
                except ValueError as exc:
                    raise HTTPException(status_code=500, detail="Invalid JSON response")

                all_calls_data = []
                overall_cost_inr = 0.0  
                total_duration_seconds = 0

                for call in response_data:
                    try:
                        started_at = datetime.fromisoformat(call["startedAt"].replace('Z', '+00:00'))
                        ended_at = datetime.fromisoformat(call["endedAt"].replace('Z', '+00:00'))
                        duration = ended_at - started_at
                        total_duration_seconds += duration.total_seconds()
                        minutes, seconds = divmod(duration.seconds, 60)
                        duration_str = f"{minutes} minutes {seconds} seconds"
                        total_cost_usd = call["costBreakdown"]["total"]
                        call_cost_inr = round(total_cost_usd * USD_TO_INR*1.2, 2)
                        overall_cost_inr += call_cost_inr
                        
                        all_calls_data.append({
                            "call_id": call["id"],
                            "phone_number_id": call["phoneNumberId"],
                            "call_type": call["type"],
                            "startedAt": started_at.isoformat(),
                            "endedAt": ended_at.isoformat(),
                            "duration": duration_str,
                            "summary": call.get("summary", "No summary available"),
                            "customer_number": call["customer"]["number"],
                            "customer_name": call["customer"]["name"],
                            "recording_url": call["recordingUrl"],
                            "status": call["status"],
                            "ended_reason": call["endedReason"],
                            "call_cost": f"\u20b9{call_cost_inr}"  
                        })
                    except KeyError as exc:
                        logger.warning(f"Missing expected key in call data: {exc}")

                total_duration_minutes = total_duration_seconds // 60
                return {
                    "total_calls": len(all_calls_data),  
                    "total_duration_minutes": total_duration_minutes,
                    "overall_cost": f"\u20b9{round(overall_cost_inr, 2)}",  
                    "calls": all_calls_data             
                }
            else:
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch calls data")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=500, detail="Failed to connect to external API")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="External API request timed out")



