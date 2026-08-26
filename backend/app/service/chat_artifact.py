import mimetypes
import shutil
import time
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

from app.core.config import CHAT_ARTIFACT_DIR, CHAT_ARTIFACT_TTL_SECONDS


class ChatArtifactNotFoundError(FileNotFoundError):
    pass


_lock = Lock()


def ensure_chat_artifact_directory() -> None:
    CHAT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_expired_chat_artifacts() -> None:
    ensure_chat_artifact_directory()
    cutoff = time.time() - max(CHAT_ARTIFACT_TTL_SECONDS, 60)
    with _lock:
        for directory in CHAT_ARTIFACT_DIR.iterdir():
            try:
                if directory.is_dir() and directory.stat().st_mtime < cutoff:
                    shutil.rmtree(directory)
            except FileNotFoundError:
                continue


def store_chat_artifact(source: Path, filename: str) -> dict:
    cleanup_expired_chat_artifacts()
    artifact_id = uuid4()
    directory = CHAT_ARTIFACT_DIR / str(artifact_id)
    target = directory / Path(filename).name
    with _lock:
        directory.mkdir(parents=True, exist_ok=False)
        shutil.copy2(source, target)
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return {
        "artifact_id": str(artifact_id),
        "filename": target.name,
        "media_type": media_type,
        "size_bytes": target.stat().st_size,
        "download_url": f"/api/artifacts/{artifact_id}",
        "expires_in_seconds": max(CHAT_ARTIFACT_TTL_SECONDS, 60),
    }


def get_chat_artifact(artifact_id: UUID) -> tuple[Path, str]:
    directory = CHAT_ARTIFACT_DIR / str(artifact_id)
    if not directory.is_dir():
        raise ChatArtifactNotFoundError
    files = [path for path in directory.iterdir() if path.is_file()]
    if len(files) != 1:
        raise ChatArtifactNotFoundError
    path = files[0]
    if path.stat().st_mtime < time.time() - max(CHAT_ARTIFACT_TTL_SECONDS, 60):
        shutil.rmtree(directory, ignore_errors=True)
        raise ChatArtifactNotFoundError
    return path, mimetypes.guess_type(path.name)[0] or "application/octet-stream"
