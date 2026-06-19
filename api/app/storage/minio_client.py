"""MinIO client (S3-compatible)."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Optional

from app.config import get_settings


class MinioClient:
    def __init__(self) -> None:
        from minio import Minio
        s = get_settings()
        self._client = Minio(
            s.minio_endpoint,
            access_key=s.minio_access_key,
            secret_key=s.minio_secret_key,
            secure=False,
        )
        self.bucket = s.minio_bucket
        self._public_base = s.minio_public_base_url

    async def ensure_bucket(self) -> None:
        def _ensure():
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
        await asyncio.to_thread(_ensure)

    def presigned_put(self, key: str, expires: timedelta = timedelta(minutes=10)) -> str:
        from minio import PutObjectPresignedCookie,  presigned_put_object
        # Use URL-style presign
        url = self._client.presigned_put_object(self.bucket, key, expires=expires)
        # The minio SDK returns an internal-host URL; rewrite to public host if needed.
        try:
            from urllib.parse import urlparse, urlunparse
            p = urlparse(url)
            public = urlparse(self._public_base)
            if p.netloc != public.netloc:
                url = urlunparse(p._replace(netloc=public.netloc, scheme=public.scheme))
        except Exception:
            pass
        return url

    def presigned_get(self, key: str, expires: timedelta = timedelta(minutes=5)) -> str:
        url = self._client.presigned_get_object(self.bucket, key, expires=expires)
        try:
            from urllib.parse import urlparse, urlunparse
            p = urlparse(url)
            public = urlparse(self._public_base)
            if p.netloc != public.netloc:
                url = urlunparse(p._replace(netloc=public.netloc, scheme=public.scheme))
        except Exception:
            pass
        return url

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        import io
        def _put():
            self._client.put_object(self.bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)
        await asyncio.to_thread(_put)

    async def get_bytes(self, key: str) -> bytes:
        def _get():
            r = self._client.get_object(self.bucket, key)
            try:
                return r.read()
            finally:
                r.close()
                r.release_conn()
        return await asyncio.to_thread(_get)

    async def stat(self, key: str) -> Optional[dict]:
        def _stat():
            try:
                o = self._client.stat_object(self.bucket, key)
                return {"size": o.size, "content_type": o.content_type}
            except Exception:
                return None
        return await asyncio.to_thread(_stat)


_minio_singleton: Optional[MinioClient] = None


def get_minio() -> MinioClient:
    global _minio_singleton
    if _minio_singleton is None:
        _minio_singleton = MinioClient()
    return _minio_singleton
