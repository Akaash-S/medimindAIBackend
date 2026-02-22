from fastapi import APIRouter, Depends
from app.core.security import get_current_user

router = APIRouter()

@router.get("/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    return {"conversations": []}

@router.post("/send")
async def send_message(message_data: dict, current_user: dict = Depends(get_current_user)):
    return {"status": "sent"}
