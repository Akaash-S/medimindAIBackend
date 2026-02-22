from app.core.firebase import db, firestore
from typing import Dict, Any, List, Optional

class FirestoreService:
    def __init__(self):
        self.db = db

    async def get_document(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db.collection(collection).document(document_id).get()
        return doc.to_dict() if doc.exists else None

    async def create_document(self, collection: str, document_id: str, data: Dict[str, Any]):
        return self.db.collection(collection).document(document_id).set(data)

    async def update_document(self, collection: str, document_id: str, data: Dict[str, Any]):
        return self.db.collection(collection).document(document_id).update(data)

    async def query_documents(self, collection: str, field: str, op: str, value: Any) -> List[Dict[str, Any]]:
        docs = self.db.collection(collection).where(field, op, value).stream()
        return [doc.to_dict() for doc in docs]

firestore_service = FirestoreService()
