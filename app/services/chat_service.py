from app.core.firebase import db, firestore
import uuid

class ChatService:
    @staticmethod
    async def initialize_conversation(participant_1_id: str, participant_2_id: str, p1_name: str, p1_role: str, p2_name: str, p2_role: str):
        """
        Creates a conversation between two users if it doesn't already exist.
        """
        # Sanitize names and roles
        p1_name = p1_name or "Patient"
        p1_role = p1_role or "patient"
        p2_name = p2_name or "Doctor"
        p2_role = p2_role or "doctor"

        # Check if conversation already exists
        existing = db.collection("conversations") \
            .where("participant_ids", "array_contains", participant_1_id) \
            .stream()

        for doc in existing:
            data = doc.to_dict()
            if participant_2_id in data.get("participant_ids", []):
                return doc.id  # already exists

        conv_id = f"auto_{participant_1_id}_{participant_2_id}"
        conversation = {
            "id": conv_id,
            "participant_ids": [participant_1_id, participant_2_id],
            "participants": {
                participant_1_id: {"name": p1_name, "role": p1_role},
                participant_2_id: {"name": p2_name, "role": p2_role},
            },
            "last_message": "Conversation started. You can now chat with each other.",
            "last_message_at": firestore.SERVER_TIMESTAMP,
            "created_at": firestore.SERVER_TIMESTAMP,
            "is_auto_generated": True
        }

        db.collection("conversations").document(conv_id).set(conversation)

        # Add initial "system" message to the subcollection
        msg_id = f"init_{conv_id}"
        initial_msg = {
            "id": msg_id,
            "sender_id": "system",
            "sender_name": "MediMind AI",
            "sender_role": "system",
            "text": f"Dr. {p2_name} has been assigned to {p1_name}'s care profile. You can now communicate securely.",
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        db.collection("conversations").document(conv_id).collection("messages").document(msg_id).set(initial_msg)

        return conv_id

chat_service = ChatService()
