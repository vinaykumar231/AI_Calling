from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
import httpx
from datetime import datetime

router = APIRouter()

# Constants
API_BASE_URL = "https://api-west.millis.ai/agents/{agent_id}/call-histories"
API_KEY = "3Ho77YuTjhnikJ00bBCIfcZaE5dnVfgz"
USD_TO_INR = 85.56

@router.get("/agents/{agent_id}/call-histories")
async def get_agent_call_histories(
    agent_id: str,
    # limit: Optional[int] = Query(100, ge=1, le=100),
    # start_at: Optional[str] = Query(None),
    include_costs: bool = Query(True, description="Include cost calculations in response")
):
    """
    Retrieve call histories for a specific agent with optional cost calculations
    """
    headers = {
        "Authorization": API_KEY,
        "Content-Type": "application/json",
    }

    # params = {"limit": limit}
    # if start_at:
    #     params["start_at"] = start_at

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = API_BASE_URL.format(agent_id=agent_id)
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Initialize counters for the summary
                total_calls = 0
                successful_calls = 0
                failed_calls = 0
                total_duration_minutes = 0
                total_cost_inr = 0
                total_cost_usd = 0

                # Manually calculate totals for cost and duration and enrich call data
                for item in data["items"]:
                    # Add timestamp in readable format
                    if "ts" in item:
                        item["timestamp"] = datetime.fromtimestamp(item["ts"]).isoformat()

                    # Add cost information if available
                    if "cost_breakdown" in item and include_costs:
                        try:
                            # Initialize the cost components
                            costs = {
                                "stt_cost": 0.0,
                                "llm_cost": 0.0,
                                "millis_cost": 0.0,
                                "total_cost_usd": 0.0,
                                "total_cost_inr": 0.0
                            }

                            # Calculate the individual cost components
                            for cost_item in item["cost_breakdown"]:
                                if cost_item["type"] == "stt":
                                    costs["stt_cost"] = cost_item["credit"]
                                elif cost_item["type"] == "llm":
                                    costs["llm_cost"] = cost_item["credit"]
                                elif cost_item["type"] == "millis":
                                    costs["millis_cost"] = cost_item["credit"]

                            # Calculate the total cost in USD and INR
                            costs["total_cost_usd"] = (costs["stt_cost"] + costs["llm_cost"] + costs["millis_cost"])
                            costs["total_cost_inr"] = round(costs["total_cost_usd"] * USD_TO_INR * 1.2, 2)

                            # Add the calculated costs to the item
                            item["costs"] = costs
                            item["total_cost_usd"] = costs["total_cost_usd"]
                            item["total_cost_inr"] = costs["total_cost_inr"]

                        except Exception as e:
                            raise ValueError(f"Error calculating costs: {str(e)}")

                    # Add call duration in minutes if available
                    if "duration" in item:
                        item["duration_minutes"] = round(item["duration"] / 60, 2)

                    # Update the summary
                    total_calls += 1
                    if item.get("call_status") == "user-ended":
                        successful_calls += 1
                    if item.get("call_status") == "failed":
                        failed_calls += 1
                    
                    total_duration_minutes += item.get("duration", 0) / 60
                    total_cost_inr += item.get("costs", {}).get("total_cost_inr", 0)
                    total_cost_usd += item.get("costs", {}).get("total_cost_usd", 0)
                
                # Add summary statistics
                data["summary"] = {
                    "total_calls": total_calls,
                    "successful_calls": successful_calls,
                    "failed_calls": failed_calls,
                    "total_duration_minutes": round(total_duration_minutes, 2),
                    "total_cost_inr": round(total_cost_inr, 2),
                    "total_cost_usd": round(total_cost_usd, 2)
                }

                data["has_histories"] = bool(data["items"])
                return data
            
            error_mapping = {
                400: "Invalid request parameters",
                401: "Invalid API key or unauthorized access",
                403: "Forbidden - insufficient permissions",
                404: f"Agent not found: {agent_id}",
                429: "Rate limit exceeded"
            }
            
            error_message = error_mapping.get(
                response.status_code, 
                f"API request failed: {response.text}"
            )
            
            raise HTTPException(status_code=response.status_code, detail=error_message)

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502, 
            detail=f"Network error while connecting to Millis API: {str(e)}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing call history data: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )
