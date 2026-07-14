const state = {
  events: [],
  max: 500,
  selected: null,
  timer: null,
};

const els = {
  autoRefresh: document.getElementById("autoRefresh"),
  refreshBtn: document.getElementById("refreshBtn"),
  clearBtn: document.getElementById("clearBtn"),
  eventCount: document.getElementById("eventCount"),
  visibleCount: document.getElementById("visibleCount"),
  lastUpdate: document.getElementById("lastUpdate"),
  filterEvent: document.getElementById("filterEvent"),
  filterModel: document.getElementById("filterModel"),
  filterUser: document.getElementById("filterUser"),
  filterConversation: document.getElementById("filterConversation"),
  filterGeneration: document.getElementById("filterGeneration"),
  filterSearch: document.getElementById("filterSearch"),
  eventsBody: document.getElementById("eventsBody"),
  modal: document.getElementById("modal"),
  modalTitle: document.getElementById("modalTitle"),
  modalMeta: document.getElementById("modalMeta"),
  modalJson: document.getElementById("modalJson"),
  copyBtn: document.getElementById("copyBtn"),
  closeBtn: document.getElementById("closeBtn"),
};

function shortId(value) {
  if (!value) return "—";
  return value.length > 10 ? `${value.slice(0, 8)}…` : value;
}

function formatTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    month: "short",
    day: "2-digit",
  });
}

function badgeClass(eventName) {
  if (eventName === "beforeSubmitPrompt") return "badge prompt";
  if (eventName === "afterMCPExecution") return "badge mcp";
  if (eventName === "preCompact") return "badge compact";
  if (eventName === "afterFileEdit") return "badge edit";
  if (eventName === "beforeShellExecution") return "badge shell";
  return "badge";
}

function badgeLabel(eventName) {
  if (eventName === "beforeSubmitPrompt") return "Prompt";
  if (eventName === "afterMCPExecution") return "MCP";
  if (eventName === "preCompact") return "Compact";
  if (eventName === "afterFileEdit") return "File Edit";
  if (eventName === "beforeShellExecution") return "Shell";
  return eventName || "Unknown";
}

function recordToolName(event) {
  return event.tool_name || event.payload?.tool_name || null;
}

function recordMcpServerName(event) {
  return event.mcp_server_name || event.payload?.mcp_server_name || null;
}

function recordPermission(event) {
  return event.permission || event.payload?.hook_decision || null;
}

function decisionCell(permission) {
  if (!permission) return "—";
  const safe = escapeHtml(permission);
  return `<span class="decision ${safe}">${safe}</span>`;
}

function recordUserEmail(event) {
  return event.user_email || event.payload?.user_email || null;
}

function populateSelect(select, values, current) {
  const previous = current || select.value;
  select.innerHTML = '<option value="">All</option>';
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }
  if (previous && values.includes(previous)) {
    select.value = previous;
  }
}

function deriveFacets(events) {
  const facets = {
    event: new Set(),
    model: new Set(),
    user_email: new Set(),
    conversation_id: new Set(),
    generation_id: new Set(),
  };

  for (const event of events) {
    if (event.event) facets.event.add(event.event);
    if (event.model) facets.model.add(event.model);
    const userEmail = recordUserEmail(event);
    if (userEmail) facets.user_email.add(userEmail);
    if (event.conversation_id) facets.conversation_id.add(event.conversation_id);
    if (event.generation_id) facets.generation_id.add(event.generation_id);
  }

  return {
    event: [...facets.event].sort(),
    model: [...facets.model].sort(),
    user_email: [...facets.user_email].sort(),
    conversation_id: [...facets.conversation_id].sort(),
    generation_id: [...facets.generation_id].sort(),
  };
}

function getFilters() {
  return {
    event: els.filterEvent.value,
    model: els.filterModel.value,
    user_email: els.filterUser.value,
    conversation_id: els.filterConversation.value,
    generation_id: els.filterGeneration.value,
    search: els.filterSearch.value.trim().toLowerCase(),
  };
}

function matchesFilters(record, filters) {
  if (filters.event && record.event !== filters.event) return false;
  if (filters.model && record.model !== filters.model) return false;
  if (filters.user_email && recordUserEmail(record) !== filters.user_email) return false;
  if (filters.conversation_id && record.conversation_id !== filters.conversation_id) return false;
  if (filters.generation_id && record.generation_id !== filters.generation_id) return false;

  if (filters.search) {
    const haystack = JSON.stringify(record).toLowerCase();
    if (!haystack.includes(filters.search)) return false;
  }

  return true;
}

function renderTable() {
  const filters = getFilters();
  const visible = state.events.filter((event) => matchesFilters(event, filters));

  els.eventCount.textContent = `${state.events.length} / ${state.max}`;
  els.visibleCount.textContent = String(visible.length);

  if (!visible.length) {
    els.eventsBody.innerHTML =
      '<tr><td colspan="9" class="empty">No events match the current filters.</td></tr>';
    return;
  }

  els.eventsBody.innerHTML = visible
    .map(
      (event) => `
        <tr data-id="${event.id}">
          <td>${formatTime(event.received_at)}</td>
          <td><span class="${badgeClass(event.event)}">${badgeLabel(event.event)}</span></td>
          <td class="user mono" title="${escapeHtml(recordUserEmail(event) || "")}">${recordUserEmail(event) ? escapeHtml(recordUserEmail(event)) : "—"}</td>
          <td class="mono" title="${escapeHtml(event.model || "")}">${event.model || "—"}</td>
          <td class="mcp-server mono" title="${escapeHtml(recordMcpServerName(event) || "")}">${recordMcpServerName(event) ? escapeHtml(recordMcpServerName(event)) : "—"}</td>
          <td class="tool mono" title="${escapeHtml(recordToolName(event) || "")}">${recordToolName(event) ? escapeHtml(recordToolName(event)) : "—"}</td>
          <td>${decisionCell(recordPermission(event))}</td>
          <td class="mono" title="${event.conversation_id || ""}">${shortId(event.conversation_id)}</td>
          <td class="summary" title="${escapeHtml(event.summary || "")}">${escapeHtml(event.summary || "—")}</td>
        </tr>
      `
    )
    .join("");

  for (const row of els.eventsBody.querySelectorAll("tr[data-id]")) {
    row.addEventListener("click", () => {
      const id = Number(row.dataset.id);
      const record = state.events.find((event) => event.id === id);
      if (record) openModal(record);
    });
  }
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function syntaxHighlightJson(value) {
  const json = JSON.stringify(value, null, 2);
  return escapeHtml(json)
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
      let cls = "json-number";
      if (/^"/.test(match)) {
        cls = /:$/.test(match) ? "json-key" : "json-string";
      } else if (/true|false/.test(match)) {
        cls = "json-boolean";
      } else if (/null/.test(match)) {
        cls = "json-null";
      }
      return `<span class="${cls}">${match}</span>`;
    });
}

function openModal(record) {
  state.selected = record;
  els.modalTitle.textContent = `${badgeLabel(record.event)} · #${record.id}`;
  const serverName = recordMcpServerName(record);
  const toolName = recordToolName(record);
  const mcpSuffix =
    serverName && toolName
      ? ` · ${serverName}/${toolName}`
      : toolName
        ? ` · ${toolName}`
        : serverName
          ? ` · ${serverName}`
          : "";
  els.modalMeta.textContent = `${recordUserEmail(record) || "unknown user"} · ${record.model || "unknown model"}${mcpSuffix} · ${record.conversation_id || "no conversation"} · ${record.generation_id || "no generation"}`;
  els.modalJson.innerHTML = syntaxHighlightJson(record);
  els.modal.classList.remove("hidden");
  els.modal.setAttribute("aria-hidden", "false");
}

function closeModal() {
  state.selected = null;
  els.modal.classList.add("hidden");
  els.modal.setAttribute("aria-hidden", "true");
}

async function fetchEvents() {
  const response = await fetch("/api/events");
  if (!response.ok) throw new Error("Failed to fetch events");
  const data = await response.json();
  state.events = data.events || [];
  state.max = data.max || 500;

  const facets = deriveFacets(state.events);
  populateSelect(els.filterEvent, facets.event, els.filterEvent.value);
  populateSelect(els.filterModel, facets.model, els.filterModel.value);
  populateSelect(els.filterUser, facets.user_email, els.filterUser.value);
  populateSelect(els.filterConversation, facets.conversation_id, els.filterConversation.value);
  populateSelect(els.filterGeneration, facets.generation_id, els.filterGeneration.value);

  renderTable();
  els.lastUpdate.textContent = new Date().toLocaleTimeString();
}

async function clearEvents() {
  if (!window.confirm("Clear all captured events?")) return;
  await fetch("/api/events", { method: "DELETE" });
  await fetchEvents();
}

function scheduleRefresh() {
  if (state.timer) clearInterval(state.timer);
  if (!els.autoRefresh.checked) return;
  state.timer = setInterval(() => {
    fetchEvents().catch(console.error);
  }, 2000);
}

els.refreshBtn.addEventListener("click", () => fetchEvents().catch(console.error));
els.clearBtn.addEventListener("click", () => clearEvents().catch(console.error));
els.autoRefresh.addEventListener("change", scheduleRefresh);
els.closeBtn.addEventListener("click", closeModal);
els.modal.addEventListener("click", (event) => {
  if (event.target.dataset.close === "true") closeModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModal();
});

els.copyBtn.addEventListener("click", async () => {
  if (!state.selected) return;
  const text = JSON.stringify(state.selected, null, 2);
  await navigator.clipboard.writeText(text);
  els.copyBtn.textContent = "Copied";
  setTimeout(() => {
    els.copyBtn.textContent = "Copy JSON";
  }, 1200);
});

for (const select of [
  els.filterEvent,
  els.filterModel,
  els.filterUser,
  els.filterConversation,
  els.filterGeneration,
]) {
  select.addEventListener("change", renderTable);
}
els.filterSearch.addEventListener("input", renderTable);

fetchEvents().catch(console.error);
scheduleRefresh();
