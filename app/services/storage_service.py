from supabase import create_client, Client
from app.core.config import settings
import httpx

class StorageService:
    def __init__(self):
        self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

    async def get_upload_url(self, bucket: str, path: str):
        # Generate a signed URL for uploading
        # Note: Supabase-py doesn't have a direct async signed upload URL method yet, 
        # normally you'd use the REST API directly or wait for sdk update.
        # This is a representative implementation.
        return self.client.storage.from_(bucket).create_signed_upload_url(path)

    async def download_file(self, bucket: str, path: str):
        return self.client.storage.from_(bucket).download(path)

storage_service = StorageService()
