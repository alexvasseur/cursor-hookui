"""Self-tests for the hook capture server."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from server.app import MAX_EVENTS, _events, app, reset_store_for_tests

ROOT = Path(__file__).resolve().parent
CAPTURE_SCRIPT = ROOT / ".cursor" / "hooks" / "capture.sh"


def sample_prompt_payload() -> dict:
    return {
        "hook_event_name": "beforeSubmitPrompt",
        "conversation_id": "conv-123",
        "generation_id": "gen-456",
        "model": "auto",
        "model_id": "claude-sonnet-4",
        "user_email": "demo@cursor.com",
        "prompt": "Build a hook capture UI",
        "attachments": [],
    }


def sample_mcp_payload() -> dict:
    return {
        "hook_event_name": "afterMCPExecution",
        "conversation_id": "conv-789",
        "generation_id": "gen-101",
        "model": "gpt-4.1",
        "user_email": "demo@cursor.com",
        "tool_name": "search",
        "mcp_server_name": "atlassian",
        "tool_input": '{"query":"hooks"}',
        "result_json": '{"items":[]}',
        "duration": 321,
    }


def sample_compact_payload() -> dict:
    return {
        "hook_event_name": "preCompact",
        "conversation_id": "conv-123",
        "generation_id": "gen-456",
        "model": "auto",
        "model_id": "claude-sonnet-4",
        "user_email": "demo@cursor.com",
        "trigger": "auto",
        "context_usage_percent": 85,
        "context_tokens": 120000,
        "context_window_size": 128000,
        "message_count": 45,
        "messages_to_compact": 30,
        "is_first_compaction": False,
    }


def sample_file_edit_payload() -> dict:
    return {
        "hook_event_name": "afterFileEdit",
        "conversation_id": "conv-321",
        "generation_id": "gen-654",
        "model": "auto",
        "user_email": "demo@cursor.com",
        "file_path": "/repo/server/app.py",
        "edits": [{"old_string": "a", "new_string": "b"}],
    }


def sample_shell_payload(decision: str = "ask") -> dict:
    return {
        "hook_event_name": "beforeShellExecution",
        "conversation_id": "conv-987",
        "generation_id": "gen-159",
        "model": "auto",
        "user_email": "demo@cursor.com",
        "command": "curl https://example.com",
        "hook_decision": decision,
        "hook_reason": "Sensitive command flagged for review by governance hook.",
    }


def test_ingest_and_list_events() -> None:
    reset_store_for_tests()
    client = TestClient(app)

    response = client.post("/ingest", json=sample_prompt_payload())
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    response = client.post("/ingest", json=sample_mcp_payload())
    assert response.status_code == 200

    response = client.get("/api/events")
    body = response.json()
    assert body["count"] == 2
    assert body["max"] == MAX_EVENTS

    newest, oldest = body["events"]
    assert newest["event"] == "afterMCPExecution"
    assert newest["summary"] == "atlassian / search (321ms)"
    assert newest["tool_name"] == "search"
    assert newest["mcp_server_name"] == "atlassian"
    assert newest["user_email"] == "demo@cursor.com"
    assert oldest["event"] == "beforeSubmitPrompt"
    assert oldest["summary"] == "Build a hook capture UI"
    assert oldest["tool_name"] is None
    assert oldest["mcp_server_name"] is None
    assert oldest["user_email"] == "demo@cursor.com"
    assert oldest["model"] == "auto → claude-sonnet-4"
    assert oldest["model_id"] == "claude-sonnet-4"


def test_precompact_summary_and_fields() -> None:
    reset_store_for_tests()
    client = TestClient(app)

    response = client.post("/ingest", json=sample_compact_payload())
    assert response.status_code == 200

    record = client.get("/api/events").json()["events"][0]
    assert record["event"] == "preCompact"
    assert record["user_email"] == "demo@cursor.com"
    assert record["summary"] == "120,000 / 128,000 ctx tokens · 85%"


def test_file_edit_and_shell_records() -> None:
    reset_store_for_tests()
    client = TestClient(app)

    client.post("/ingest", json=sample_file_edit_payload())
    client.post("/ingest", json=sample_shell_payload("ask"))

    events = client.get("/api/events").json()["events"]
    shell_record, edit_record = events

    assert edit_record["event"] == "afterFileEdit"
    assert edit_record["file_path"] == "/repo/server/app.py"
    assert edit_record["summary"] == "/repo/server/app.py (1 edit)"
    assert edit_record["permission"] is None

    assert shell_record["event"] == "beforeShellExecution"
    assert shell_record["command"] == "curl https://example.com"
    assert shell_record["permission"] == "ask"
    assert shell_record["summary"] == "[ask] curl https://example.com"


def test_shell_deny_decision_recorded() -> None:
    reset_store_for_tests()
    client = TestClient(app)

    payload = sample_shell_payload("deny")
    payload["command"] = "rm -rf /"
    client.post("/ingest", json=payload)

    record = client.get("/api/events").json()["events"][0]
    assert record["permission"] == "deny"
    assert record["summary"] == "[deny] rm -rf /"


def test_facets_and_clear() -> None:
    reset_store_for_tests()
    client = TestClient(app)
    client.post("/ingest", json=sample_prompt_payload())
    client.post("/ingest", json=sample_mcp_payload())

    response = client.get("/api/facets")
    facets = response.json()
    assert "beforeSubmitPrompt" in facets["event"]
    assert "afterMCPExecution" in facets["event"]
    assert "demo@cursor.com" in facets["user_email"]
    assert "auto → claude-sonnet-4" in facets["model"]
    assert "conv-123" in facets["conversation_id"]

    response = client.delete("/api/events")
    assert response.json()["count"] == 0
    assert client.get("/api/events").json()["count"] == 0


def test_eviction_at_500() -> None:
    reset_store_for_tests()
    client = TestClient(app)

    for index in range(505):
        payload = sample_prompt_payload()
        payload["prompt"] = f"event-{index}"
        client.post("/ingest", json=payload)

    body = client.get("/api/events").json()
    assert body["count"] == MAX_EVENTS
    assert body["events"][0]["summary"] == "event-504"
    assert body["events"][-1]["summary"] == "event-5"


def test_malformed_ingest_does_not_crash() -> None:
    reset_store_for_tests()
    client = TestClient(app)

    response = client.post("/ingest", content="not-json", headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert client.get("/api/events").json()["count"] == 1


def test_enrich_legacy_record_fields() -> None:
    reset_store_for_tests()
    client = TestClient(app)
    client.post("/ingest", json=sample_mcp_payload())

    record = _events[0]
    del record["tool_name"]
    del record["mcp_server_name"]
    del record["user_email"]

    body = client.get("/api/events").json()
    assert body["events"][0]["tool_name"] == "search"
    assert body["events"][0]["mcp_server_name"] == "atlassian"
    assert body["events"][0]["user_email"] == "demo@cursor.com"


def test_capture_script_silent_fail_without_backend() -> None:
    env = {"HOOK_UI_PORT": "1"}
    prompt = subprocess.run(
        [str(CAPTURE_SCRIPT)],
        input=json.dumps(sample_prompt_payload()),
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **env},
    )
    assert prompt.returncode == 0
    assert json.loads(prompt.stdout) == {"continue": True}

    mcp = subprocess.run(
        [str(CAPTURE_SCRIPT)],
        input=json.dumps(sample_mcp_payload()),
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **env},
    )
    assert mcp.returncode == 0
    assert json.loads(mcp.stdout) == {}


def _run_capture(payload: dict) -> dict:
    result = subprocess.run(
        [str(CAPTURE_SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "HOOK_UI_PORT": "1"},
    )
    assert result.returncode == 0
    return json.loads(result.stdout)


def test_capture_script_shell_governance() -> None:
    if not shutil.which("jq"):
        print("SKIP test_capture_script_shell_governance (jq not installed)")
        return

    deny = _run_capture({"hook_event_name": "beforeShellExecution", "command": "rm -rf /"})
    assert deny["permission"] == "deny"

    ask = _run_capture({"hook_event_name": "beforeShellExecution", "command": "curl https://example.com"})
    assert ask["permission"] == "ask"

    allow = _run_capture({"hook_event_name": "beforeShellExecution", "command": "ls -la"})
    assert allow["permission"] == "allow"

    edit = _run_capture({"hook_event_name": "afterFileEdit", "file_path": "/repo/x.py"})
    assert edit == {}


def run() -> None:
    tests = [
        test_ingest_and_list_events,
        test_precompact_summary_and_fields,
        test_file_edit_and_shell_records,
        test_shell_deny_decision_recorded,
        test_facets_and_clear,
        test_eviction_at_500,
        test_malformed_ingest_does_not_crash,
        test_enrich_legacy_record_fields,
        test_capture_script_silent_fail_without_backend,
        test_capture_script_shell_governance,
    ]

    for test in tests:
        test()
        print(f"PASS {test.__name__}")

    print(f"All {len(tests)} tests passed")


if __name__ == "__main__":
    run()
