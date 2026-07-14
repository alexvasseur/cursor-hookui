#!/bin/bash
# Cursor hook: forward hook payloads to the local capture server and, for
# beforeShellExecution, apply a simple governance policy (allow / ask / deny).
# Silently no-ops (fails open) if the backend is unavailable.

set -uo pipefail

input=$(cat)

PORT="${HOOK_UI_PORT:-8765}"

event_name=$(printf '%s' "$input" | jq -r '.hook_event_name // empty' 2>/dev/null || echo "")

# Governance decision — only meaningful for beforeShellExecution.
decision="allow"
reason=""

if [ "$event_name" = "beforeShellExecution" ]; then
  command=$(printf '%s' "$input" | jq -r '.command // empty' 2>/dev/null || echo "")

  if [[ "$command" == *':()'* ]] \
    || [[ "$command" =~ rm[[:space:]]+-rf[[:space:]]+(/|~) ]] \
    || [[ "$command" == *mkfs* ]] \
    || { [[ "$command" == *"dd if="* ]] && [[ "$command" == *"of=/dev/"* ]]; } \
    || [[ "$command" =~ git[[:space:]]+push[[:space:]].*--force ]]; then
    decision="deny"
    reason="Destructive command blocked by governance hook."
  elif [[ "$command" =~ (^|[[:space:]])sudo[[:space:]] ]] \
    || [[ "$command" =~ (^|[[:space:]])(curl|wget|nc)[[:space:]] ]] \
    || [[ "$command" =~ git[[:space:]]+push ]] \
    || [[ "$command" =~ rm[[:space:]]+-rf[[:space:]] ]]; then
    decision="ask"
    reason="Sensitive command flagged for review by governance hook."
  fi
fi

# Enrich the payload with the governance decision so the UI can display it.
if command -v jq >/dev/null 2>&1; then
  posted=$(printf '%s' "$input" | jq -c --arg d "$decision" --arg r "$reason" \
    '. + {hook_decision: $d, hook_reason: $r}' 2>/dev/null || printf '%s' "$input")
else
  posted="$input"
fi

printf '%s' "$posted" | curl -s --max-time 1 \
  -X POST "http://127.0.0.1:${PORT}/ingest" \
  -H 'Content-Type: application/json' \
  --data-binary @- \
  >/dev/null 2>&1 &
disown 2>/dev/null || true

case "$event_name" in
  beforeSubmitPrompt)
    printf '%s\n' '{"continue": true}'
    ;;
  beforeShellExecution)
    case "$decision" in
      deny)
        printf '{"permission": "deny", "user_message": %s, "agent_message": %s}\n' \
          "$(printf '%s' "$reason" | jq -R .)" "$(printf '%s' "$reason" | jq -R .)"
        ;;
      ask)
        printf '{"permission": "ask", "user_message": %s}\n' \
          "$(printf '%s' "$reason" | jq -R .)"
        ;;
      *)
        printf '%s\n' '{"permission": "allow"}'
        ;;
    esac
    ;;
  afterMCPExecution|preCompact|afterFileEdit)
    printf '%s\n' '{}'
    ;;
  *)
    printf '%s\n' '{}'
    ;;
esac

exit 0
