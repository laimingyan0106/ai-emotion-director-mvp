from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

import httpx

from ..config import get_settings


class MediaStorage(ABC):
    @abstractmethod
    async def put(
        self,
        pathname: str,
        source: BinaryIO,
        *,
        content_type: str | None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        raise NotImplementedError


class LocalMediaStorage(MediaStorage):
    def __init__(self, root: Path) -> None:
        self.root = root

    async def put(
        self,
        pathname: str,
        source: BinaryIO,
        *,
        content_type: str | None,
    ) -> str:
        del content_type
        root = self.root.resolve()
        target = (root / pathname).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Media pathname escapes storage root")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
        return str(target)

    async def delete(self, storage_path: str) -> None:
        root = self.root.resolve()
        target = Path(storage_path).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Media path escapes storage root")
        target.unlink(missing_ok=True)
        directory = target.parent
        while directory != root and directory.is_relative_to(root):
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent


class VercelBlobMediaStorage(MediaStorage):
    def __init__(self) -> None:
        self.token = os.environ["BLOB_READ_WRITE_TOKEN"]

    async def put(
        self,
        pathname: str,
        source: BinaryIO,
        *,
        content_type: str | None,
    ) -> str:
        headers = {
            "authorization": f"Bearer {self.token}",
            "x-vercel-blob-access": "private",
            "x-api-version": "12",
            "x-content-type": content_type or "application/octet-stream",
            "x-add-random-suffix": "0",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.put(
                "https://blob.vercel-storage.com",
                params={"pathname": pathname},
                headers=headers,
                content=source.read(),
            )
            response.raise_for_status()
        result = response.json()
        return str(result["url"])

    async def delete(self, storage_path: str) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://blob.vercel-storage.com/delete",
                headers={
                    "authorization": f"Bearer {self.token}",
                    "x-api-version": "12",
                },
                json={"urls": [storage_path]},
            )
            response.raise_for_status()


def get_media_storage() -> MediaStorage:
    settings = get_settings()
    if settings.resolved_media_storage_mode == "vercel_blob":
        return VercelBlobMediaStorage()
    return LocalMediaStorage(settings.resolved_media_root)
