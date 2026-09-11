"""JSON-file document store.

Each document is stored as ``<id>.json`` inside ``data/docs/``. Writes are
atomic (tmp file + os.replace) and guarded by an asyncio lock so concurrent
requests cannot corrupt a document.
"""

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from . import config

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_lock = asyncio.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(doc_id: str) -> str:
    return os.path.join(config.DOCS_DIR, f"{doc_id}.json")


def new_id() -> str:
    return uuid.uuid4().hex


def _read(doc_id: str) -> dict[str, Any] | None:
    try:
        with open(_path(doc_id), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write(doc_id: str, doc: dict[str, Any]) -> None:
    tmp = f"{_path(doc_id)}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False)
    os.replace(tmp, _path(doc_id))


def _summary(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc["id"],
        "title": doc.get("title", "Untitled"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


def sanitize_id(doc_id: str) -> str | None:
    if not _ID_RE.match(doc_id):
        return None
    return doc_id


async def list_docs() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for name in os.listdir(config.DOCS_DIR):
        if not name.endswith(".json"):
            continue
        doc = _read(name[: -len(".json")])
        if doc:
            docs.append(_summary(doc))
    docs.sort(key=lambda d: d.get("updatedAt") or "", reverse=True)
    return docs


async def get_doc(doc_id: str) -> dict[str, Any] | None:
    doc_id = sanitize_id(doc_id)
    if doc_id is None:
        return None
    return _read(doc_id)


async def create_doc(title: str, content: Any) -> dict[str, Any]:
    now = _now()
    doc: dict[str, Any] = {
        "id": new_id(),
        "title": title,
        "content": content,
        "createdAt": now,
        "updatedAt": now,
    }
    async with _lock:
        _write(doc["id"], doc)
    return doc


async def update_doc(
    doc_id: str, title: str | None, content: Any
) -> dict[str, Any] | None:
    doc_id = sanitize_id(doc_id)
    if doc_id is None:
        return None
    async with _lock:
        doc = _read(doc_id)
        if doc is None:
            return None
        if title is not None:
            doc["title"] = title
        if content is not None:
            doc["content"] = content
        doc["updatedAt"] = _now()
        _write(doc_id, doc)
    return doc


async def delete_doc(doc_id: str) -> bool:
    doc_id = sanitize_id(doc_id)
    if doc_id is None:
        return False
    async with _lock:
        if not os.path.exists(_path(doc_id)):
            return False
        os.remove(_path(doc_id))
    return True