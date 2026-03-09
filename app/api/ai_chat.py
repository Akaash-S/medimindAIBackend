import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from groq import AsyncGroq
from app.core.config import settings
from app.core.firebase import db
from app.core.security import get_current_user
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

router = APIRouter()

# The API key provided by the user in the prompt
groq_client = AsyncGroq(api_key=settings.GROQ_MED_API_KEY)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    patient_context_id: Optional[str] = None

async def _get_patient_context(patient_uid: str) -> str:
    """Fetches patient profile and recent reports to build a contextual prompt."""
    try:
        user_doc = db.collection("users").document(patient_uid).get()
        if not user_doc.exists:
            return ""
        
        user_data = user_doc.to_dict()
        
        # Get recent reports
        reports_ref = db.collection("reports").where("user_id", "==", patient_uid).limit(3)
        reports = list(reports_ref.stream())
        
        context = f"Patient Profile:\n"
        context += f"- Age: {user_data.get('age', 'Unknown')}\n"
        context += f"- Gender: {user_data.get('gender', 'Unknown')}\n"
        context += f"- Blood Group: {user_data.get('blood_group', 'Unknown')}\n"
        context += f"- Known Conditions: {user_data.get('conditions', 'None reported')}\n"
        context += f"- Allergies: {user_data.get('allergies', 'None reported')}\n\n"
        
        if reports:
            context += "Recent Medical Reports Context:\n"
            for doc in reports:
                rd = doc.to_dict()
                ai = rd.get("analysis", {})
                if ai:
                    context += f"- Report '{rd.get('file_name', 'Unknown')}': Risk Level [{ai.get('risk_level', 'Unknown')}]. Summary: {ai.get('summary', 'No summary.')}\n"
                    
        return context
    except Exception as e:
        print(f"Error fetching patient context: {e}")
        return ""

@router.post("/")
async def chat_stream(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """Stream an AI chat response using Groq."""
    
    system_prompt = "You are a highly skilled Medical AI Assistant named 'MediMind AI'. You analyze medical data, answer health questions, and provide guidance based on context. Note: You must always explicitly state that you are an AI and your advice does not replace a professional medical consultation.\n\n"
    
    # Context Logic
    role = current_user.get("role", "patient")
    target_patient_id = req.patient_context_id if role == "doctor" else current_user["uid"]
    
    if target_patient_id:
        patient_context = await _get_patient_context(target_patient_id)
        if patient_context:
            system_prompt += f"Here is the relevant clinical context for the patient you are discussing:\n{patient_context}\n\nUse this information to personalize your answer if applicable. If the user asks about their conditions or reports, refer to this data."

    # Build messages array for Groq
    messages = [{"role": "system", "content": system_prompt}]
    
    for msg in req.messages:
        # Sanitize roles just in case
        safe_role = "assistant" if msg.role == "ai" else ("user" if msg.role == "user" else "user")
        messages.append({"role": safe_role, "content": msg.content})

    async def generate():
        try:
            stream = await groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7, # Slightly lower than 1 to keep medical answers focused
                max_completion_tokens=1024,
                top_p=1,
                stream=True,
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            print(f"Groq streaming error: {e}")
            yield "I'm sorry, I encountered an error processing your request."

    return StreamingResponse(generate(), media_type="text/event-stream")
