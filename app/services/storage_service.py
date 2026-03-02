import httpx
from app.core.config import settings


class StorageService:
    """
    Supabase Storage helper using direct HTTP calls to the Storage REST API.
    This avoids all Python SDK version compatibility issues between v1 and v2.
    """

    def __init__(self):
        self.base_url = settings.SUPABASE_URL.rstrip("/")
        self.service_key = settings.SUPABASE_SERVICE_KEY
        self.headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
        }

    async def get_upload_url(self, bucket: str, path: str) -> dict:
        """
        Create a signed upload URL via the Supabase Storage REST API.

        Correct Supabase endpoint:
          POST /storage/v1/object/upload/sign/{bucket}/{path}
          Body: { "expiresIn": <seconds> }

        Response: { "url": "/object/upload/sign/{bucket}/{path}?token=...", "token": "..." }
        The client must then PUT the file to: {SUPABASE_URL}/storage/v1{url}
        """
        endpoint = f"{self.base_url}/storage/v1/object/upload/sign/{bucket}/{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                endpoint,
                headers={**self.headers, "Content-Type": "application/json"},
                json={"expiresIn": 3600},
                timeout=15,
            )

        print(f"Supabase signed upload URL [{resp.status_code}]: {resp.text[:400]}")

        if resp.status_code not in (200, 201):
            raise Exception(
                f"Supabase returned {resp.status_code} for signed upload URL: {resp.text}"
            )

        data = resp.json()
        # Response shape: {"url": "/object/upload/sign/bucket/path?token=...", "token": "..."}
        relative_url = data.get("url") or data.get("signedURL") or data.get("signed_url", "")
        if not relative_url:
            raise Exception(f"No URL field in Supabase signed upload response: {data}")

        # Build the full absolute URL the frontend will PUT the file to
        signed_url = (
            f"{self.base_url}/storage/v1{relative_url}"
            if relative_url.startswith("/")
            else relative_url
        )

        return {"signedURL": signed_url, "path": path}

    async def download_file(self, bucket: str, path: str) -> bytes:
        """Download a file from Supabase Storage."""
        url = f"{self.base_url}/storage/v1/object/{bucket}/{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers, timeout=30)
        if resp.status_code != 200:
            raise Exception(f"Supabase download failed [{resp.status_code}]: {resp.text}")
        return resp.content

    async def delete_file(self, bucket: str, path: str):
        """Delete a file from Supabase Storage."""
        url = f"{self.base_url}/storage/v1/object/{bucket}/{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.delete(url, headers=self.headers, timeout=15)
        if resp.status_code not in (200, 204):
            raise Exception(f"Supabase delete failed [{resp.status_code}]: {resp.text}")
        return resp.json() if resp.content else {}


storage_service = StorageService()
