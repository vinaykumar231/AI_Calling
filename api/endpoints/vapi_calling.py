import json
import os
import requests
from fastapi import FastAPI, Request
from pydantic import BaseModel

# FastAPI app setup
app = FastAPI()

# Exotel API details
EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN =os.getenv("EXOTEL_API_TOKEN")
EXOTEL_URL = "https://api.exotel.com/v1/Accounts/{}/Calls/connect.json".format(EXOTEL_ACCOUNT_SID)

# VAPI API details
VAPI_URL = "https://api.vapi.ai/call"
VAPI_API_KEY =os.getenv("VAPI_API_KEY")

# Step 1: Make a call using Exotel API
def initiate_call(from_number, to_number, webhook_url):
    # Prepare Exotel request payload
    data = {
        "From": from_number,
        "To": to_number,
        "CallerId": from_number,
        "Url": webhook_url  # Your server's webhook URL where Exotel will send updates
    }
    
    # Making the request to Exotel to initiate the call
    try:
        response = requests.post(EXOTEL_URL, data=data, auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN))
        # Check if the response is successful
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Exotel API failed with status {response.status_code}: {response.text}"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request error: {str(e)}"}

@app.post("/exotel-webhook")
async def exotel_webhook(request: Request):
    headers = request.headers
    content_type = headers.get("Content-Type")

    # Log the headers to help debug
    print("Request Headers:", headers)

    if content_type is None:
        return {"error": "Missing Content-Type header"}

    if "application/json" in content_type:
        raw_body = await request.body()
        print("Raw request body:", raw_body)

        if raw_body:
            try:
                data = json.loads(raw_body)
                print("Received Exotel Webhook:", data)

                # Example: Check the CallStatus and trigger VAPI
                if data.get("CallStatus") == "completed":
                    customer_number = data.get("To")
                    print(f"Call completed. Customer number: {customer_number}")

                    # Prepare VAPI payload
                    vapi_payload = {
                        "call_id": data.get("CallSid"),
                        "customer_number": customer_number
                    }

                    # Sending VAPI API request for AI interaction
                    vapi_headers = {
                        "Authorization": f"Bearer {VAPI_API_KEY}"
                    }

                    try:
                        vapi_response = requests.post(VAPI_URL, json=vapi_payload, headers=vapi_headers)
                        print("VAPI Response Status:", vapi_response.status_code)

                        if vapi_response.status_code == 200:
                            return {"message": "VAPI AI interaction triggered successfully"}
                        else:
                            return {"error": "Failed to trigger VAPI", "details": vapi_response.json()}
                    except requests.exceptions.RequestException as e:
                        return {"error": f"VAPI request error: {str(e)}"}

                else:
                    return {"message": "Call not answered or ended"}
            except json.JSONDecodeError:
                return {"error": "Failed to decode JSON"}
        else:
            return {"error": "Empty request body"}
    else:
        return {"error": f"Unsupported Content-Type: {content_type}"}

# Step 4: Initiate the call
@app.get("/initiate-call")
async def initiate_call_endpoint():
    # The phone numbers to call
    from_number = '040-491-71102'  # Exotel number
    to_number = '+919004173181'  # Recipient's number
    
    # Webhook URL that Exotel will call
    webhook_url = "https://hook.eu2.make.com/14jfu2nxkd87vqfbbyl5y34gzmp65rsy"  # Replace with your actual URL
    
    # Initiate call via Exotel
    response = initiate_call(from_number, to_number, webhook_url)
    
    return response
