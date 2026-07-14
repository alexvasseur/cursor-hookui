#!/usr/bin/env python3
"""Seed the hook capture server with synthetic events."""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from uuid import uuid4

MODELS = [
    "auto",
    "claude-sonnet-4",
    "gpt-4.1",
    "composer-1",
    "claude-opus-4",
]

TOOLS = [
    "search",
    "getJiraIssue",
    "execute_zapier_read_action",
    "CallMcpTool",
    "fetch",
]

PROMPTS = [
    "Refactor the auth middleware to use dependency injection.",
    "Add unit tests for the ingest endpoint.",
    "Why is the MCP hook not firing in cloud agents?",
    "Generate a demo dataset with mixed prompt and MCP events.",
    "Show me the last 20 intercepted events for this conversation.",
]


def build_prompt_event(conversation_id: str, generation_id: str, model: str) -> dict:
    model_id = "claude-opus-4-8-thinking-high" if model == "auto" else None
    payload = {
        "hook_event_name": "beforeSubmitPrompt",
        "conversation_id": conversation_id,
        "generation_id": generation_id,
        "model": model,
        "cursor_version": "1.7.2",
        "workspace_roots": ["/Users/demo/cursor-hookui"],
        "user_email": "demo@cursor.com",
        "prompt": random.choice(PROMPTS),
        "attachments": [
            {
                "type": "file",
                "file_path": "/Users/demo/cursor-hookui/server/app.py",
            }
        ],
    }
    if model_id:
        payload["model_id"] = model_id
    return payload


def build_mcp_event(conversation_id: str, generation_id: str, model: str) -> dict:
    tool_name = random.choice(TOOLS)
    return {
        "hook_event_name": "afterMCPExecution",
        "conversation_id": conversation_id,
        "generation_id": generation_id,
        "model": model,
        "cursor_version": "1.7.2",
        "workspace_roots": ["/Users/demo/cursor-hookui"],
        "user_email": "demo@cursor.com",
        "tool_name": tool_name,
        "tool_input": json.dumps({"query": "hook capture", "limit": 10}),
        "result_json": json.dumps({"ok": True, "items": [{"id": 1, "name": "sample"}]}),
        "duration": random.randint(120, 2400),
    }


def post_event(base_url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/ingest",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected status: {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed hook capture events")
    parser.add_argument("--count", type=int, default=75, help="Number of events to create")
    parser.add_argument("--demo", action="store_true", help="Use demo-friendly defaults")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8765",
        help="Hook capture server base URL",
    )
    args = parser.parse_args()

    count = 100 if args.demo and args.count == 75 else args.count
    conversations = [str(uuid4()) for _ in range(max(3, count // 20))]

    try:
        for index in range(count):
            conversation_id = random.choice(conversations)
            generation_id = str(uuid4())
            model = random.choice(MODELS)
            payload = (
                build_prompt_event(conversation_id, generation_id, model)
                if index % 2 == 0
                else build_mcp_event(conversation_id, generation_id, model)
            )
            post_event(args.base_url, payload)
    except urllib.error.URLError as exc:
        print(f"Failed to reach server at {args.base_url}: {exc}", file=sys.stderr)
        print("Start the server first with ./run.sh", file=sys.stderr)
        return 1

    print(f"Seeded {count} events to {args.base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
