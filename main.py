from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine
from api.endpoints import (user_router, dashboard_router, millisai_api_router,Bolna_calling_router,Razorpay_gatway_router, subscription_Plan_router)
Base.metadata.create_all(bind=engine)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(user_router, prefix="/api", tags=["user Routes"])
app.include_router(dashboard_router, prefix="/api", tags=[" Vapi dashboard data Routes"])
app.include_router(millisai_api_router, prefix="/api", tags=[" millisai_api_router Routes"])
app.include_router(Bolna_calling_router, prefix="/api", tags=[" Bolna calling Routes"])
app.include_router(Razorpay_gatway_router, prefix="/api", tags=[" Razorpay Routes"])
app.include_router(subscription_Plan_router, prefix="/api", tags=[" subscription Plan Routes"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8000, reload= True, host="0.0.0.0")