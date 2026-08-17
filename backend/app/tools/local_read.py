import fnmatch
import os
import shutil
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from app.core.config import (
    AGENT_WORKSPACE_DIR,
    LOCAL_READ_MAX_CHARS,
    LOCAL_SEARCH_MAX_RESULTS,
)


class LocalPathError(ValueError):
    pass


def ensure_workspace_directory() -> Path:
    """Create the configured sandbox root before any Agent tool can use it."""
    AGENT_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    return AGENT_WORKSPACE_DIR.resolve()


def resolve_workspace_path(relative_path: str = ".") -> Path:
    root = AGENT_WORKSPACE_DIR.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise LocalPathError("路径不能超出 Agent 工作区") from error
    return candidate


def _memory_status() -> dict[str, int] | None:
    path = Path("/proc/meminfo")
    if not path.exists():
        return None
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, raw = line.partition(":")
        if key in {"MemTotal", "MemAvailable"}:
            values[key] = int(raw.strip().split()[0]) * 1024
    if "MemTotal" not in values or "MemAvailable" not in values:
        return None
    return {
        "total_bytes": values["MemTotal"],
        "available_bytes": values["MemAvailable"],
        "used_bytes": values["MemTotal"] - values["MemAvailable"],
    }


def _temperature() -> float | None:
    for path in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")):
        try:
            value = float(path.read_text(encoding="ascii").strip())
            return round(value / 1000 if value > 200 else value, 1)
        except (OSError, ValueError):
            continue
    return None


@tool
def local_system_status() -> dict[str, Any]:
    """读取 Nano 后端容器的负载、内存、工作区磁盘、运行时间和温度。"""
    root = AGENT_WORKSPACE_DIR.resolve()
    usage = shutil.disk_usage(root if root.exists() else root.parent)
    try:
        load_average = list(os.getloadavg())
    except OSError:
        load_average = []
    uptime_path = Path("/proc/uptime")
    uptime = (
        float(uptime_path.read_text(encoding="ascii").split()[0])
        if uptime_path.exists()
        else None
    )
    return {
        "load_average_1m_5m_15m": load_average,
        "memory": _memory_status(),
        "workspace_disk": {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        },
        "uptime_seconds": uptime,
        "temperature_celsius": _temperature(),
    }


@tool
def local_list_files(relative_path: str = ".", max_entries: int = 100) -> dict:
    """列出 Agent 工作区内一个目录的文件；路径必须相对于受限工作区。"""
    path = resolve_workspace_path(relative_path)
    if not path.is_dir():
        return {
            "entries": [],
            "truncated": False,
            "exists": False,
            "message": "目录不存在；如需写入可直接创建目标文件及其父目录",
        }
    limit = min(max(1, max_entries), LOCAL_SEARCH_MAX_RESULTS)
    entries = []
    for item in sorted(path.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower())):
        stat = item.stat()
        entries.append({
            "path": item.relative_to(AGENT_WORKSPACE_DIR.resolve()).as_posix(),
            "kind": "directory" if item.is_dir() else "file",
            "size_bytes": stat.st_size if item.is_file() else None,
            "modified_at": stat.st_mtime,
        })
        if len(entries) >= limit:
            break
    return {"entries": entries, "truncated": len(entries) >= limit, "exists": True}


@tool
def local_read_text(relative_path: str, max_chars: int = 20000) -> dict:
    """读取 Agent 工作区内 UTF-8/GB18030 文本文件的有限长度内容。"""
    path = resolve_workspace_path(relative_path)
    if not path.is_file():
        raise LocalPathError("文件不存在")
    limit = min(max(1, max_chars), LOCAL_READ_MAX_CHARS)
    raw = path.read_bytes()[: limit * 4 + 1]
    text = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise LocalPathError("文件不是支持的文本编码")
    return {
        "path": relative_path,
        "content": text[:limit],
        "truncated": len(text) > limit or len(raw) > limit * 4,
    }


@tool
def local_search_files(
    pattern: str,
    relative_path: str = ".",
    max_results: int = 50,
) -> dict:
    """按文件名 glob 在 Agent 工作区内递归搜索文件，例如 *.md。"""
    root = resolve_workspace_path(relative_path)
    if not root.is_dir():
        return {
            "matches": [],
            "truncated": False,
            "exists": False,
            "message": "搜索目录不存在",
        }
    limit = min(max(1, max_results), LOCAL_SEARCH_MAX_RESULTS)
    matches = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name for name in directories if not (Path(current) / name).is_symlink()
        )
        for filename in sorted(filenames):
            if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                path = Path(current) / filename
                matches.append({
                    "path": path.relative_to(AGENT_WORKSPACE_DIR.resolve()).as_posix(),
                    "size_bytes": path.stat().st_size,
                })
                if len(matches) >= limit:
                    return {"matches": matches, "truncated": True, "exists": True}
    return {"matches": matches, "truncated": False, "exists": True}


def create_local_read_tools():
    return [local_system_status, local_list_files, local_read_text, local_search_files]
