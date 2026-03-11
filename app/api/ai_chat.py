import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from groq import AsyncGroq
from app.core.config import settings
from app.core.firebase import db, firestore
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
    conversation_id: Optional[str] = None

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

@router.get("/conversations")
async def get_ai_conversations(current_user: dict = Depends(get_current_user)):
    """Get all AI chat sessions for the current user."""
    try:
        uid = current_user["uid"]
        # Fetch without order_by to avoid composite index requirements
        docs = db.collection("ai_conversations") \
            .where("user_id", "==", uid) \
            .stream()
        
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            results.append(data)
            
        # Manually sort by updated_at (descending)
        def get_sort_key(x):
            ts = x.get("updated_at") or x.get("created_at")
            if hasattr(ts, 'isoformat'):
                return ts.isoformat()
            return str(ts or "")

        results.sort(key=get_sort_key, reverse=True)
        
        return results
    except Exception as e:
        print(f"Error fetching AI conversations: {e}")
        # Return empty list or raise 500
        return []

@router.get("/conversations/{conv_id}/messages")
async def get_ai_messages(conv_id: str, current_user: dict = Depends(get_current_user)):
    """Get all messages in an AI chat session."""
    uid = current_user["uid"]
    conv_ref = db.collection("ai_conversations").document(conv_id)
    conv_doc = conv_ref.get()
    
    if not conv_doc.exists or conv_doc.to_dict().get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Access denied")
    
    messages = conv_ref.collection("messages").order_by("created_at").stream()
    return [{**m.to_dict(), "id": m.id} for m in messages]

@router.delete("/conversations/{conv_id}")
async def delete_ai_conversation(conv_id: str, current_user: dict = Depends(get_current_user)):
    """Delete an AI chat session."""
    uid = current_user["uid"]
    conv_ref = db.collection("ai_conversations").document(conv_id)
    conv_doc = conv_ref.get()
    
    if not conv_doc.exists or conv_doc.to_dict().get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Simple recursive deletion for demo purposes (small scale)
    msgs = conv_ref.collection("messages").stream()
    for m in msgs:
        m.reference.delete()
    conv_ref.delete()
    return {"status": "success"}

@router.post("")
async def chat_stream(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """Stream an AI chat response using Groq and persist to Firestore."""
    uid = current_user["uid"]
    role = current_user.get("role", "patient")
    target_patient_id = req.patient_context_id if role == "doctor" else uid
    
    # 1. Manage Conversation ID
    conv_id = req.conversation_id
    if not conv_id:
        conv_id = str(uuid.uuid4())
        db.collection("ai_conversations").document(conv_id).set({
            "user_id": uid,
            "title": req.messages[-1].content[:50] + "...",
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
    else:
        db.collection("ai_conversations").document(conv_id).update({
            "updated_at": firestore.SERVER_TIMESTAMP
        })

    conv_ref = db.collection("ai_conversations").document(conv_id)

    # 2. Build system prompt with context
    system_prompt = "You are a highly skilled Medical AI Assistant named 'MediMind AI'. You analyze medical data, answer health questions, and provide guidance based on context. Note: You must always explicitly state that you are an AI and your advice does not replace a professional medical consultation.\n\n"
    
    if target_patient_id:
        patient_context = await _get_patient_context(target_patient_id)
        if patient_context:
            system_prompt += f"Here is the relevant clinical context for the patient you are discussing:\n{patient_context}\n\nUse this information to personalize your answer if applicable."

    # 3. Build messages array for Groq
    groq_messages = [{"role": "system", "content": system_prompt}]
    for msg in req.messages:
        safe_role = "assistant" if msg.role == "ai" else "user"
        groq_messages.append({"role": safe_role, "content": msg.content})

    # 4. Save User's message
    last_user_msg = req.messages[-1].content
    conv_ref.collection("messages").add({
        "role": "user",
        "content": last_user_msg,
        "created_at": firestore.SERVER_TIMESTAMP
    })

    async def generate():
        total_ai_content = ""
        try:
            stream = await groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=groq_messages,
                temperature=0.7,
                max_completion_tokens=1024,
                top_p=1,
                stream=True,
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    total_ai_content += content
                    yield content
            
            # 5. Save AI's response after full stream
            conv_ref.collection("messages").add({
                "role": "ai",
                "content": total_ai_content,
                "created_at": firestore.SERVER_TIMESTAMP
            })
            # Add conversation ID to first chunk or as a separate header if needed
            # For simplicity in this demo, the frontend will track the conv_id it sent or received
        except Exception as e:
            print(f"Groq streaming error: {e}")
            yield "\n[Error: Connection lost. Response may be incomplete.]"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"X-Conversation-Id": conv_id})
