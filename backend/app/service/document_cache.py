import hashlib
import os
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from threading import Lock
from typing import BinaryIO
from uuid import uuid4

from app.core.config import DOCUMENT_CACHE_DIR, DOCUMENT_CACHE_MAX_BYTES


class DocumentCacheError(RuntimeError):
    pass


Downloader = Callable[[str, Path], None]


class DocumentCache:
    def __init__(self, directory: Path, maximum_bytes: int) -> None:
        self.directory = directory
        self.maximum_bytes = maximum_bytes
        self._lock = Lock()

    def path_for(self, object_key: str) -> Path:
        digest = hashlib.sha256(object_key.encode()).hexdigest()
        suffix = PurePosixPath(object_key).suffix.lower()
        return self.directory / f"{digest}{suffix}"

    def ensure(
        self,
        object_key: str,
        expected_size: int,
        expected_checksum: str,
        downloader: Downloader,
    ) -> Path:
        path = self.path_for(object_key)
        with self._lock:
            if self._is_valid_size(path, expected_size):
                self._touch(path)
                return path

            self._unlink(path)
            self._require_capacity(expected_size)
            temporary = self.directory / f".{path.name}.{uuid4().hex}.tmp"
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                downloader(object_key, temporary)
                self._validate_file(temporary, expected_size, expected_checksum)
                self._evict_for(expected_size)
                os.replace(temporary, path)
                self._touch(path)
                return path
            except DocumentCacheError:
                raise
            except OSError as error:
                raise DocumentCacheError("写入本地文档缓存失败") from error
            finally:
                self._unlink(temporary)

    def store_stream(
        self,
        object_key: str,
        stream: BinaryIO,
        expected_size: int,
        expected_checksum: str,
    ) -> Path:
        path = self.path_for(object_key)
        with self._lock:
            self._require_capacity(expected_size)
            temporary = self.directory / f".{path.name}.{uuid4().hex}.tmp"
            digest = hashlib.sha256()
            size = 0
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                with temporary.open("wb") as target:
                    while chunk := stream.read(1024 * 1024):
                        target.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                if size != expected_size or digest.hexdigest() != expected_checksum:
                    raise DocumentCacheError("写入本地缓存时文件校验失败")
                self._unlink(path)
                self._evict_for(expected_size)
                os.replace(temporary, path)
                self._touch(path)
                return path
            except OSError as error:
                raise DocumentCacheError("写入本地文档缓存失败") from error
            finally:
                self._unlink(temporary)

    def read_bytes(self, path: Path, maximum_bytes: int) -> bytes:
        try:
            if path.stat().st_size > maximum_bytes:
                raise DocumentCacheError("文档内容超过预览大小限制")
            self._touch(path)
            return path.read_bytes()
        except OSError as error:
            raise DocumentCacheError("读取本地文档缓存失败") from error

    def remove(self, object_key: str) -> None:
        with self._lock:
            self._unlink(self.path_for(object_key))

    def _validate_file(
        self,
        path: Path,
        expected_size: int,
        expected_checksum: str,
    ) -> None:
        try:
            if path.stat().st_size != expected_size:
                raise DocumentCacheError("云端文件大小与文档记录不一致")
            digest = hashlib.sha256()
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != expected_checksum:
                raise DocumentCacheError("云端文件校验失败")
        except OSError as error:
            raise DocumentCacheError("校验本地文档缓存失败") from error

    def _evict_for(self, incoming_bytes: int) -> None:
        try:
            cached_files = [
                path
                for path in self.directory.iterdir()
                if path.is_file() and not path.name.startswith(".")
            ]
            entries = []
            for path in cached_files:
                stat = path.stat()
                entries.append((stat.st_atime_ns, stat.st_size, path))
            total = sum(size for _, size, _ in entries)
            for _, size, path in sorted(entries):
                if total + incoming_bytes <= self.maximum_bytes:
                    break
                path.unlink(missing_ok=True)
                total -= size
            if total + incoming_bytes > self.maximum_bytes:
                raise DocumentCacheError("本地文档缓存空间不足")
        except DocumentCacheError:
            raise
        except OSError as error:
            raise DocumentCacheError("清理本地文档缓存失败") from error

    def _require_capacity(self, size: int) -> None:
        if self.maximum_bytes <= 0:
            raise DocumentCacheError("本地文档缓存已禁用")
        if size > self.maximum_bytes:
            raise DocumentCacheError("文档大小超过本地缓存容量")

    @staticmethod
    def _is_valid_size(path: Path, expected_size: int) -> bool:
        try:
            return path.is_file() and path.stat().st_size == expected_size
        except OSError:
            return False

    @staticmethod
    def _touch(path: Path) -> None:
        try:
            stat = path.stat()
            os.utime(path, ns=(time.time_ns(), stat.st_mtime_ns))
        except OSError as error:
            raise DocumentCacheError("更新本地文档缓存失败") from error

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise DocumentCacheError("清理本地文档缓存失败") from error


document_cache = DocumentCache(DOCUMENT_CACHE_DIR, DOCUMENT_CACHE_MAX_BYTES)
