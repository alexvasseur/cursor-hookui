"""FastAPI server for capturing Cursor hook events in memory."""

from __future__ import annotations

import itertools
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

MAX_EVENTS = 500
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Cursor Hook Capture UI")
_events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
_id_counter = itertools.count(1)


def reset_store_for_tests() -> None:
    """Reset in-memory state for unit tests."""
    global _id_counter
    _events.clear()
    _id_counter = itertools.count(1)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _display_model(payload: dict[str, Any]) -> str | None:
    model = _as_str(payload.get("model"))
    model_id = _as_str(payload.get("model_id"))
    if model_id and model_id != model:
        return f"{model or 'auto'} → {model_id}"
    return model


def _file_path(payload: dict[str, Any]) -> str | None:
    return _as_str(payload.get("file_path")) or _as_str(payload.get("path"))


def _build_summary(payload: dict[str, Any]) -> str:
    event = payload.get("hook_event_name")
    if event == "beforeSubmitPrompt":
        return _truncate(_as_str(payload.get("prompt")))
    if event == "afterMCPExecution":
        server_name = _as_str(payload.get("mcp_server_name"))
        tool_name = _as_str(payload.get("tool_name")) or "unknown tool"
        label = f"{server_name} / {tool_name}" if server_name else tool_name
        duration = payload.get("duration")
        if isinstance(duration, (int, float)):
            return f"{label} ({int(duration)}ms)"
        return label
    if event == "preCompact":
        context_tokens = payload.get("context_tokens")
        context_window_size = payload.get("context_window_size")
        usage = payload.get("context_usage_percent")
        if isinstance(context_tokens, (int, float)) and isinstance(context_window_size, (int, float)):
            parts = [f"{int(context_tokens):,} / {int(context_window_size):,} ctx tokens"]
            if isinstance(usage, (int, float)):
                parts.append(f"{int(usage)}%")
            return " · ".join(parts)
    if event == "afterFileEdit":
        path = _file_path(payload)
        edits = payload.get("edits")
        if path and isinstance(edits, list):
            noun = "edit" if len(edits) == 1 else "edits"
            return _truncate(f"{path} ({len(edits)} {noun})")
        return _truncate(path or "file edit")
    if event == "beforeShellExecution":
        command = _as_str(payload.get("command")) or "(no command)"
        decision = _as_str(payload.get("hook_decision"))
        if decision:
            return _truncate(f"[{decision}] {command}")
        return _truncate(command)
    return _truncate(_as_str(event) or "event")


def _build_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": next(_id_counter),
        "received_at": _utc_now_iso(),
        "event": _as_str(payload.get("hook_event_name")),
        "model": _display_model(payload),
        "model_id": _as_str(payload.get("model_id")),
        "user_email": _as_str(payload.get("user_email")),
        "conversation_id": _as_str(payload.get("conversation_id")),
        "generation_id": _as_str(payload.get("generation_id")),
        "tool_name": _as_str(payload.get("tool_name")),
        "mcp_server_name": _as_str(payload.get("mcp_server_name")),
        "command": _as_str(payload.get("command")),
        "file_path": _file_path(payload),
        "permission": _as_str(payload.get("hook_decision")),
        "summary": _build_summary(payload),
        "payload": payload,
    }


def _enrich_record(record: dict[str, Any]) -> dict[str, Any]:
    """Backfill derived fields for records stored by an older server build."""
    payload = record.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    enriched = dict(record)
    if not enriched.get("tool_name"):
        enriched["tool_name"] = _as_str(payload.get("tool_name"))
    if not enriched.get("mcp_server_name"):
        enriched["mcp_server_name"] = _as_str(payload.get("mcp_server_name"))
    if not enriched.get("command"):
        enriched["command"] = _as_str(payload.get("command"))
    if not enriched.get("file_path"):
        enriched["file_path"] = _file_path(payload)
    if not enriched.get("permission"):
        enriched["permission"] = _as_str(payload.get("hook_decision"))
    if not enriched.get("user_email"):
        enriched["user_email"] = _as_str(payload.get("user_email"))
    if not enriched.get("model_id"):
        enriched["model_id"] = _as_str(payload.get("model_id"))
    if not enriched.get("model"):
        enriched["model"] = _display_model(payload)
    return enriched


def _facet_values(key: str) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for record in _events:
        value = record.get(key)
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return sorted(values)


@app.post("/ingest")
async def ingest(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {"raw": payload}

    _events.appendleft(_build_record(payload))
    return JSONResponse({"ok": True})


@app.get("/api/events")
async def list_events() -> JSONResponse:
    return JSONResponse(
        {
            "count": len(_events),
            "max": MAX_EVENTS,
            "events": [_enrich_record(record) for record in _events],
        }
    )


@app.get("/api/facets")
async def list_facets() -> JSONResponse:
    return JSONResponse(
        {
            "event": _facet_values("event"),
            "model": _facet_values("model"),
            "user_email": _facet_values("user_email"),
            "conversation_id": _facet_values("conversation_id"),
            "generation_id": _facet_values("generation_id"),
        }
    )


@app.delete("/api/events")
async def clear_events() -> JSONResponse:
    _events.clear()
    return JSONResponse({"ok": True, "count": 0})


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
