from supabase import create_client, Client
from app.core.config import settings
import httpx

class StorageService:
    def __init__(self):
        self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

    async def get_upload_url(self, bucket: str, path: str):
        """Generate a signed URL for uploading."""
        try:
            # Generate signed URL
            # Note: create_signed_upload_url is typically synchronous in the current SDK
            res = self.client.storage.from_(bucket).create_signed_upload_url(path)
            
            # Log the response (masked URL for security)
            print(f"Supabase signed URL response: {res}")
            
            if isinstance(res, dict):
                if "signedURL" in res:
                    return res
                if "signed_url" in res:
                    # Standardize to signedURL for the outer logic
                    return {"signedURL": res["signed_url"]}
                return res
            
            # Some versions might return it in a different format or wrapped
            if hasattr(res, "data"):
                data = res.data
                if isinstance(data, dict):
                    if "signed_url" in data and "signedURL" not in data:
                        data["signedURL"] = data["signed_url"]
                return data
            
            raise Exception(f"Unexpected response format from Supabase: {res}")
        except Exception as e:
            print(f"Error generating signed upload URL for bucket '{bucket}', path '{path}': {e}")
            raise e

    async def download_file(self, bucket: str, path: str):
        try:
            return self.client.storage.from_(bucket).download(path)
        except Exception as e:
            print(f"Error downloading file from bucket '{bucket}', path '{path}': {e}")
            raise e

storage_service = StorageService()
