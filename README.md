# Cursor Hook Capture UI

**See what Cursor's agent is doing — and govern it — in real time.**

This repo wires [Cursor Hooks](https://cursor.com/docs/agent/hooks) into a live dashboard. Every time the agent submits a prompt, calls an MCP tool, edits a file, compacts context, or runs a shell command, the hook fires, the event lands in the UI, and you can inspect or act on it.

Hook capture dashboard

## What you get

- **Visibility** — a rolling feed of agent activity: prompts, MCP calls, file edits, context compaction, and shell commands, with user, model, conversation, and full JSON payloads.
- **Governance** — the `beforeShellExecution` hook applies allow / ask / deny rules (e.g. block destructive commands, flag `sudo` or `git push` for review) before the agent runs anything.
- **Zero friction** — hooks fail open if the dashboard isn't running; Cursor keeps working normally.


![Demo UI](https://github.com/alexvasseur/cursor-hookui/blob/main/docs/screenshot.png?raw=true)


## Hooks in this repo

Configured in `[.cursor/hooks.json](.cursor/hooks.json)`, all routed through `[.cursor/hooks/capture.sh](.cursor/hooks/capture.sh)`:


| Hook                   | Outcome                                                    |
| ---------------------- | ---------------------------------------------------------- |
| `beforeSubmitPrompt`   | Capture the prompt (and attachments) before the agent runs |
| `afterMCPExecution`    | Capture MCP tool name, server, duration, and result        |
| `afterFileEdit`        | Capture which file changed and how many edits              |
| `preCompact`           | Capture context-window usage when compaction triggers      |
| `beforeShellExecution` | Capture the command **and** return allow / ask / deny      |




## Try it

```bash
./run.sh
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765), then use Cursor in this workspace — events appear as you chat, call tools, and run commands.

Optional demo data:

```bash
python seed.py --demo
```



## Why hooks?

Hooks sit on the agent lifecycle itself. They let teams **observe** what agents do across prompts, tools, and terminals, and **enforce policy** at the moment of action — without changing how developers use Cursor day to day.