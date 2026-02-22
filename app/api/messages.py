import html
import re
from fastapi import APIRouter, Depends, HTTPException
from app.core.firebase import db, firestore
from app.core.security import get_current_user
import uuid

router = APIRouter()


def sanitize_text(text: str) -> str:
    """Sanitize message text to prevent XSS and injection attacks."""
    if not text or not isinstance(text, str):
        return ""
    # Strip leading/trailing whitespace
    text = text.strip()
    # HTML-entity-encode dangerous characters
    text = html.escape(text, quote=True)
    # Limit length
    if len(text) > 5000:
        text = text[:5000]
    return text


@router.get("/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    """Get all conversations the current user is a participant in."""
    uid = current_user["uid"]

    docs = db.collection("conversations") \
        .where("participant_ids", "array_contains", uid) \
        .stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)

    # Sort by last_message_at descending
    results.sort(
        key=lambda x: x.get("last_message_at", "") or "",
        reverse=True
    )
    return results


@router.post("/conversations")
async def create_conversation(conv_data: dict, current_user: dict = Depends(get_current_user)):
    """Start a new conversation with another user."""
    uid = current_user["uid"]
    other_id = conv_data.get("other_user_id", "")
    other_name = sanitize_text(conv_data.get("other_user_name", ""))
    other_role = conv_data.get("other_user_role", "doctor")

    if not other_id:
        raise HTTPException(status_code=400, detail="other_user_id is required")

    # Check if conversation already exists between these two users
    existing = db.collection("conversations") \
        .where("participant_ids", "array_contains", uid) \
        .stream()

    for doc in existing:
        data = doc.to_dict()
        if other_id in data.get("participant_ids", []):
            data["id"] = doc.id
            return data  # return the existing conversation

    conv_id = str(uuid.uuid4())
    my_name = current_user.get("full_name") or current_user.get("name", "Patient")
    my_role = current_user.get("role", "patient")

    conversation = {
        "id": conv_id,
        "participant_ids": [uid, other_id],
        "participants": {
            uid: {"name": my_name, "role": my_role},
            other_id: {"name": other_name, "role": other_role},
        },
        "last_message": "",
        "last_message_at": firestore.SERVER_TIMESTAMP,
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    db.collection("conversations").document(conv_id).set(conversation)

    # Re-read to get resolved timestamps
    created = db.collection("conversations").document(conv_id).get().to_dict()
    created["id"] = conv_id
    return created


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """Get all messages in a conversation. Verifies participant access."""
    uid = current_user["uid"]

    # Verify the user is a participant
    conv_ref = db.collection("conversations").document(conversation_id)
    conv_doc = conv_ref.get()
    if not conv_doc.exists:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv_data = conv_doc.to_dict()
    if uid not in conv_data.get("participant_ids", []):
        raise HTTPException(status_code=403, detail="Access denied")

    # Fetch messages ordered by created_at
    msgs = conv_ref.collection("messages") \
        .order_by("created_at") \
        .stream()

    results = []
    for msg in msgs:
        data = msg.to_dict()
        data["id"] = msg.id
        results.append(data)

    return results


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, message_data: dict, current_user: dict = Depends(get_current_user)):
    """Send a message in a conversation. Sanitizes input to prevent XSS."""
    uid = current_user["uid"]
    text = sanitize_text(message_data.get("text", ""))

    if not text:
        raise HTTPException(status_code=400, detail="Message text is required")

    # Verify the user is a participant
    conv_ref = db.collection("conversations").document(conversation_id)
    conv_doc = conv_ref.get()
    if not conv_doc.exists:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv_data = conv_doc.to_dict()
    if uid not in conv_data.get("participant_ids", []):
        raise HTTPException(status_code=403, detail="Access denied")

    msg_id = str(uuid.uuid4())
    sender_name = current_user.get("full_name") or current_user.get("name", "User")

    message = {
        "id": msg_id,
        "sender_id": uid,
        "sender_name": sender_name,
        "sender_role": current_user.get("role", "patient"),
        "text": text,
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    # Add message to subcollection
    conv_ref.collection("messages").document(msg_id).set(message)

    # Update conversation metadata
    conv_ref.update({
        "last_message": text[:100],  # Truncate for preview
        "last_message_at": firestore.SERVER_TIMESTAMP,
    })

    # Re-read to get resolved timestamps
    created = conv_ref.collection("messages").document(msg_id).get().to_dict()
    created["id"] = msg_id
    return created
