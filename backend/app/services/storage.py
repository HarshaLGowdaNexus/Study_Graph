"""
Storage Service for StudyGraph.
Relies on Decision D06: Supabase Storage.
Handles saving raw study materials (PDFs, presentations, images) into cloud storage.
"""

import os
from pathlib import Path
from typing import Optional
import httpx
from backend.app.core.config import settings


class StorageService:
    def __init__(self):
        self.bucket = settings.SUPABASE_STORAGE_BUCKET
        self.base_url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1"
        # Use service role key if available for administrative/storage actions, else anon key
        self.auth_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY

    def _get_headers(self, content_type: str = "application/octet-stream", user_token: Optional[str] = None) -> dict:
        auth_bearer = user_token or self.auth_key
        return {
            "Authorization": f"Bearer {auth_bearer}",
            "apikey": self.auth_key,
            "Content-Type": content_type,
            "x-upsert": "true",
        }

    async def ensure_bucket_exists(self) -> bool:
        """
        Checks whether the configured storage bucket exists, and creates it if missing.
        """
        if not settings.SUPABASE_URL or not self.auth_key:
            return False

        check_url = f"{self.base_url}/bucket/{self.bucket}"
        headers = {
            "Authorization": f"Bearer {self.auth_key}",
            "apikey": self.auth_key,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(check_url, headers=headers)
                if res.status_code == 200:
                    return True

                # Bucket does not exist, attempt to create it
                create_url = f"{self.base_url}/bucket"
                payload = {
                    "id": self.bucket,
                    "name": self.bucket,
                    "public": False,
                    "file_size_limit": settings.MAX_FILE_SIZE_MB * 1024 * 1024,
                    "allowed_mime_types": [
                        "application/pdf",
                        "application/vnd.ms-powerpoint",
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        "image/png",
                        "image/jpeg",
                    ],
                }
                create_res = await client.post(create_url, json=payload, headers=headers)
                return create_res.status_code in (200, 201)
        except Exception:
            return False

    async def upload_file(
        self,
        file_bytes: bytes,
        storage_path: str,
        content_type: str = "application/octet-stream",
        user_token: Optional[str] = None,
    ) -> str:
        """
        Uploads binary file data to Supabase Storage at:
        {bucket}/{storage_path}
        Returns the storage path identifier upon success.
        """
        # Testing or local fallback if remote service is unconfigured or in offline mode (R17)
        if settings.APP_ENV == "testing" or not settings.SUPABASE_URL or not self.auth_key:
            local_storage_dir = Path(settings.ROOT_DIR) / ".storage_cache" / self.bucket
            target_path = local_storage_dir / storage_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(file_bytes)
            return f"local://{self.bucket}/{storage_path}"

        # Ensure bucket exists
        await self.ensure_bucket_exists()

        upload_url = f"{self.base_url}/object/{self.bucket}/{storage_path}"
        headers = self._get_headers(content_type, user_token=user_token)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(upload_url, content=file_bytes, headers=headers)
                if res.status_code not in (200, 201):
                    # If cloud upload fails with permission, fall back to local store
                    local_dir = Path(settings.ROOT_DIR) / ".storage_cache" / self.bucket
                    local_target = local_dir / storage_path
                    local_target.parent.mkdir(parents=True, exist_ok=True)
                    local_target.write_bytes(file_bytes)
                    return f"fallback://{self.bucket}/{storage_path}"

                return f"supabase://{self.bucket}/{storage_path}"
        except Exception as e:
            # Fallback to local storage cache so user workflow is never blocked
            local_dir = Path(settings.ROOT_DIR) / ".storage_cache" / self.bucket
            local_target = local_dir / storage_path
            local_target.parent.mkdir(parents=True, exist_ok=True)
            local_target.write_bytes(file_bytes)
            return f"fallback://{self.bucket}/{storage_path}"

    async def download_file(self, storage_uri: str) -> bytes:
        """
        Downloads binary file data given a storage URI (supabase://, fallback://, local://, or relative path).
        Returns binary bytes of the file.
        """
        # Parse bucket and subpath from URI
        cleaned = storage_uri
        for prefix in ("supabase://", "fallback://", "local://"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break

        # Remove bucket name if it's the first component
        if cleaned.startswith(f"{self.bucket}/"):
            subpath = cleaned[len(f"{self.bucket}/"):]
        else:
            subpath = cleaned

        # 1. Check local cache first (works offline and for fallback/local files)
        local_target = Path(settings.ROOT_DIR) / ".storage_cache" / self.bucket / subpath
        if local_target.exists():
            return local_target.read_bytes()

        # 2. Try fetching from Supabase Storage cloud
        if settings.SUPABASE_URL and self.auth_key:
            download_url = f"{self.base_url}/object/{self.bucket}/{subpath}"
            headers = {
                "Authorization": f"Bearer {self.auth_key}",
                "apikey": self.auth_key,
            }
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.get(download_url, headers=headers)
                    if res.status_code == 200:
                        # Cache locally for fast future reads
                        local_target.parent.mkdir(parents=True, exist_ok=True)
                        local_target.write_bytes(res.content)
                        return res.content
            except Exception:
                pass

        # 3. Final check: if subpath itself is an absolute or relative path on disk
        direct_path = Path(storage_uri)
        if direct_path.exists() and direct_path.is_file():
            return direct_path.read_bytes()

        raise FileNotFoundError(f"Could not locate or download file from storage: {storage_uri}")


storage_service = StorageService()


