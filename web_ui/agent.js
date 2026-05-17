// Storage keys
const STORAGE_THEME = "datn_ui_theme";
const STORAGE_THREADS = "datn_agent_threads_v1";
const STORAGE_CHAT_LEGACY = "datn_chat_messages_v1";
const STORAGE_REMINDERS_V1 = "datn_agent_reminders_v1";
const STORAGE_REMINDERS = "datn_agent_reminders_v2";
const STORAGE_BACKEND = "datn_llm_backend";  // 'auto', 'ollama', 'openrouter'
const STORAGE_QUERY_MODE = "datn_query_mode";  // 'agent', 'neo4j-direct'

/** Application configuration constants */
const CONFIG = {
  // Storage limits (localStorage quota protection)
  MAX_CHAT_ENTRIES: 200,    // Messages per thread (prevent UI sluggishness)
  MAX_THREADS: 80,          // Total conversation threads
  MAX_REMINDERS: 100,       // Medication reminders
  
  // API limits
  MAX_MESSAGE_LENGTH: 4000,      // Characters per message
  STREAM_CHUNK_SIZE: 4,          // Characters per stream chunk (UI smoothness)
  MAX_PREVIEW_CHARS: 240,        // Log/ preview truncation
  MAX_INPUT_PREVIEW: 800,        // Tool input display limit
  MAX_LOG_CHARS: 500,            // Terminal log truncation
  MAX_ANSWER_PREVIEW: 180,       // Answer preview in logs
  MAX_ACTION_PREVIEW: 300,       // Action display limit
  
  // Retry configuration
  RETRY_ATTEMPTS: 2,             // Default fetch retries
  RETRY_DELAY_MS: 350,           // Base retry delay (exponential backoff)
  RETRY_STATUS_CODES: [502, 503, 504, 429],  // Server errors worth retrying
  
  // Timeouts
  READINESS_TIMEOUT: 3000,       // Health check timeout (ms)
  DEFAULT_API_TIMEOUT: 120000,   // 2 minutes for LLM responses
};

// Backward compatible aliases (deprecated, use CONFIG)
const MAX_CHAT_ENTRIES = CONFIG.MAX_CHAT_ENTRIES;
const MAX_THREADS = CONFIG.MAX_THREADS;
const MAX_REMINDERS = CONFIG.MAX_REMINDERS;

/** @type {{ threads: { id: string, title: string, updatedAt: number, messages: { role: string, html: string }[] }[], activeThreadId: string | null }} */
let threadState = { threads: [], activeThreadId: null };

/**
 * @typedef {{ id: string, text: string, at: string, notified?: boolean, kind?: "once" }} ReminderOnce
 * @typedef {{ id: string, text: string, kind: "daily", times: string[], lastFired?: Record<string, string> }} ReminderDaily
 * @typedef {{ id: string, text: string, kind: "interval", intervalHours: number, nextDueIso: string }} ReminderInterval
 * @type {(ReminderOnce | ReminderDaily | ReminderInterval)[]} */
let reminders = [];

function $(id) {
  return document.getElementById(id);
}

function newId(prefix) {
  return `${prefix || "id"}_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function defaultApiBase() {
  try {
    const { protocol, host } = window.location;
    if (host && (protocol === "http:" || protocol === "https:")) return `${protocol}//${host}`;
  } catch {
    /* ignore */
  }
  return "http://127.0.0.1:8000";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Retry ngắn khi lỗi mạng hoặc 502/503/504/429 (ổn định demo).
 * @param {string} url
 * @param {RequestInit} options
 * @param {{ retries?: number, retryOn?: number[] }} [cfg]
 */
async function fetchWithRetry(url, options, cfg) {
  const retries = cfg?.retries ?? CONFIG.RETRY_ATTEMPTS;
  const retryOn = cfg?.retryOn ?? CONFIG.RETRY_STATUS_CODES;
  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const r = await fetch(url, options);
      if (r.ok) return r;
      if (!retryOn.includes(r.status) || attempt >= retries) return r;
    } catch (e) {
      lastErr = e;
      if (attempt >= retries) throw e;
    }
    await sleep(CONFIG.RETRY_DELAY_MS * 2 ** attempt);
  }
  throw lastErr ?? new Error("fetchWithRetry");
}

async function runReadinessBanner() {
  const el = $("e2eReadinessBanner");
  if (!el) return;
  const base = defaultApiBase().replace(/\/$/, "");
  try {
    const r = await fetchWithRetry(`${base}/health/ready`, { method: "GET" }, { retries: 1 });
    if (!r.ok) return;
    const data = await r.json();
    if (data.agent_e2e_ready) {
      el.textContent = "";
      el.classList.add("hidden");
      return;
    }
    const parts = [];
    const o = data.ollama || {};
    // Only show Ollama error if Ollama is enabled (not when using API key)
    if (o.enabled !== false) {
      if (!o.ok) parts.push("Không kết nối được Ollama.");
      else if (!o.model_available) parts.push(`Trên Ollama chưa có model "${o.model_env || ""}" (cần ollama pull).`);
    }
    const n = data.neo4j || {};
    if (n.enabled) {
      if (!n.ok) parts.push("Không kết nối được Neo4j.");
      else if (n.graph_populated === false) parts.push("Neo4j chưa có dữ liệu GraphEntity — cần đồng bộ đồ thị.");
    } else {
      const g = data.graphrag_index || {};
      if (!g.ok) parts.push("Chưa có index GraphRAG (parquet) cho luồng CLI.");
    }
    el.textContent =
      parts.join(" ") ||
      "Luồng hỏi–đáp có thể thiếu dịch vụ phụ trợ — xem GET /health/ready trên API.";
    el.classList.remove("hidden");
  } catch {
    /* API chưa chạy — giữ banner ẩn */
  }
}

function applyTheme() {
  const saved = localStorage.getItem(STORAGE_THEME);
  let dark = false;
  if (saved === "dark") dark = true;
  else if (saved === "light") dark = false;
  else dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", dark);
  const moon = document.querySelector(".icon-moon");
  const sun = document.querySelector(".icon-sun");
  if (moon && sun) {
    moon.classList.toggle("hidden", dark);
    sun.classList.toggle("hidden", !dark);
  }
}

function toggleTheme() {
  const next = !document.documentElement.classList.contains("dark");
  localStorage.setItem(STORAGE_THEME, next ? "dark" : "light");
  applyTheme();
}

function getActiveThread() {
  if (!threadState.activeThreadId) return null;
  return threadState.threads.find((t) => t.id === threadState.activeThreadId) ?? null;
}

/** @returns {{ role: string, html: string }[]} */
function currentMessages() {
  const t = getActiveThread();
  return t ? t.messages : [];
}

function saveThreadsState() {
  try {
    localStorage.setItem(STORAGE_THREADS, JSON.stringify(threadState));
  } catch {
    while (threadState.threads.length > 1) {
      threadState.threads.pop();
      try {
        localStorage.setItem(STORAGE_THREADS, JSON.stringify(threadState));
        return;
      } catch {
        /* continue */
      }
    }
  }
}

function normalizeThread(t) {
  if (!t || typeof t.id !== "string") return null;
  const messages = Array.isArray(t.messages)
    ? t.messages.filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.html === "string")
    : [];
  return {
    id: t.id,
    title: typeof t.title === "string" && t.title.trim() ? t.title.trim() : "Cuộc trò chuyện mới",
    updatedAt: typeof t.updatedAt === "number" ? t.updatedAt : Date.now(),
    messages: messages.slice(-MAX_CHAT_ENTRIES),
  };
}

function migrateLegacyChat() {
  if (threadState.threads.length > 0) return;
  try {
    const raw = localStorage.getItem(STORAGE_CHAT_LEGACY);
    if (!raw) return;
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr) || !arr.length) return;
    const filtered = arr.filter(
      (x) => x && (x.role === "user" || x.role === "assistant") && typeof x.html === "string"
    );
    if (!filtered.length) return;
    const id = newId("t");
    threadState.threads = [
      {
        id,
        title: "Cuộc trò chuyện trước",
        updatedAt: Date.now(),
        messages: filtered.slice(-MAX_CHAT_ENTRIES),
      },
    ];
    threadState.activeThreadId = id;
    saveThreadsState();
  } catch {
    /* ignore */
  }
}

function loadThreadsState() {
  try {
    const raw = localStorage.getItem(STORAGE_THREADS);
    if (raw) {
      const data = JSON.parse(raw);
      if (data && Array.isArray(data.threads)) {
        threadState.threads = data.threads.map(normalizeThread).filter(Boolean);
        threadState.activeThreadId = typeof data.activeThreadId === "string" ? data.activeThreadId : null;
      }
    }
  } catch {
    threadState = { threads: [], activeThreadId: null };
  }
  migrateLegacyChat();
  if (!threadState.threads.length) {
    const id = newId("t");
    threadState.threads.push({ id, title: "Cuộc trò chuyện mới", updatedAt: Date.now(), messages: [] });
    threadState.activeThreadId = id;
    saveThreadsState();
  } else if (!threadState.activeThreadId || !getActiveThread()) {
    threadState.activeThreadId = threadState.threads[0].id;
    saveThreadsState();
  }
}

function sortThreadsForDisplay() {
  return [...threadState.threads].sort((a, b) => b.updatedAt - a.updatedAt);
}

function renderThreadList() {
  const ul = $("threadList");
  if (!ul) return;
  ul.innerHTML = "";
  const sorted = sortThreadsForDisplay();
  for (const t of sorted) {
    const li = document.createElement("li");
    li.className = "chat-thread-item";
    if (t.id === threadState.activeThreadId) li.classList.add("is-active");
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", t.id === threadState.activeThreadId ? "true" : "false");
    li.dataset.threadId = t.id;
    const title = document.createElement("span");
    title.className = "chat-thread-item-title";
    title.textContent = t.title;
    li.appendChild(title);
    li.addEventListener("click", () => selectThread(t.id));
    ul.appendChild(li);
  }
}

function updateThreadHeader() {
  const el = $("activeThreadTitle");
  const t = getActiveThread();
  if (el && t) el.textContent = t.title;
}

function maybeAutoTitle(thread, role, plainTextHint) {
  if (thread.title !== "Cuộc trò chuyện mới" && thread.title.length > 2) return;
  if (role !== "user" || !plainTextHint) return;
  const line = plainTextHint.trim().split(/\n/)[0];
  if (!line) return;
  const short = line.length > 48 ? `${line.slice(0, 45)}…` : line;
  thread.title = short || thread.title;
}

function createNewThread() {
  const id = newId("t");
  threadState.threads.unshift({ id, title: "Cuộc trò chuyện mới", updatedAt: Date.now(), messages: [] });
  if (threadState.threads.length > MAX_THREADS) threadState.threads = threadState.threads.slice(0, MAX_THREADS);
  threadState.activeThreadId = id;
  saveThreadsState();
  renderChatFromStorage();
  renderThreadList();
  updateThreadHeader();
  $("question")?.focus();
}

function selectThread(id) {
  if (id === threadState.activeThreadId) return;
  threadState.activeThreadId = id;
  const t = getActiveThread();
  if (t) t.updatedAt = Date.now();
  saveThreadsState();
  renderChatFromStorage();
  renderThreadList();
  updateThreadHeader();
  $("question")?.focus();
}

function deleteCurrentThread() {
  const t = getActiveThread();
  if (!t) return;
  if (!window.confirm(`Xóa cuộc trò chuyện "${t.title}"?`)) return;
  threadState.threads = threadState.threads.filter((x) => x.id !== t.id);
  if (!threadState.threads.length) {
    const id = newId("t");
    threadState.threads.push({ id, title: "Cuộc trò chuyện mới", updatedAt: Date.now(), messages: [] });
    threadState.activeThreadId = id;
  } else {
    threadState.activeThreadId = threadState.threads[0].id;
  }
  saveThreadsState();
  renderChatFromStorage();
  renderThreadList();
  updateThreadHeader();
}

function scrollChatToBottom() {
  const el = $("chatMessages");
  if (el) el.scrollTop = el.scrollHeight;
}

function renderChatFromStorage() {
  const box = $("chatMessages");
  if (!box) return;
  box.innerHTML = "";
  const msgs = currentMessages();
  for (const item of msgs) {
    appendChatBubble(item.role, item.html, { persist: false, skipScroll: true });
  }
  scrollChatToBottom();
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function appendChatBubble(role, html, options = {}) {
  const persist = options.persist !== false;
  const skipScroll = options.skipScroll === true;
  const row = document.createElement("div");
  row.className = `chat-row chat-row--${role}`;
  if (role === "user") {
    row.innerHTML = `<div class="chat-row-flex"><div class="chat-bubble chat-bubble--user">${html}</div></div>`;
  } else {
    row.innerHTML = `<div class="chat-row-flex"><span class="chat-avatar" aria-hidden="true">NV</span><div class="chat-bubble chat-bubble--assistant">${html}</div></div>`;
  }
  $("chatMessages").appendChild(row);
  if (persist) {
    const t = getActiveThread();
    if (t) {
      t.messages.push({ role, html });
      if (t.messages.length > MAX_CHAT_ENTRIES) {
        t.messages = t.messages.slice(-MAX_CHAT_ENTRIES);
      }
      t.updatedAt = Date.now();
      saveThreadsState();
    }
    renderThreadList();
  }
  if (!skipScroll) scrollChatToBottom();
}

function buildSourcesHtml(sources) {
  if (!sources.length) return "<p class=\"chat-muted\">Không có nguồn trong lượt trả lời này.</p>";
  const parts = sources.map((s, i) => {
    const title = s.title || "(không có tiêu đề)";
    const link = s.link || "";
    const src = s.source ? ` — ${s.source}` : "";
    const score = s.score != null ? ` (${Number(s.score).toFixed(4)})` : "";
    if (link) {
      return `<li><strong>[${i + 1}]</strong> ${escapeHtml(title)}${escapeHtml(src)}${score}<br><a href="${escapeAttr(link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link)}</a></li>`;
    }
    return `<li><strong>[${i + 1}]</strong> ${escapeHtml(title)}${escapeHtml(src)}${score}</li>`;
  });
  return `<ul class="chat-sources">${parts.join("")}</ul>`;
}

function escapeAttr(s) {
  return String(s).replace(/"/g, "&quot;");
}

function buildDrugImagesHtml(urls) {
  if (!Array.isArray(urls) || !urls.length) return "";
  const base = defaultApiBase().replace(/\/$/, "");
  const figures = urls.map((u) => {
    const raw = String(u || "");
    const src = /^https?:\/\//i.test(raw) ? raw : `${base}${raw.startsWith("/") ? "" : "/"}${raw}`;
    return `<figure class="chat-drug-img"><img src="${escapeAttr(src)}" alt="" loading="lazy" decoding="async" /></figure>`;
  });
  return `<div class="chat-drug-images"><h4 class="chat-sources-title">Ảnh minh họa (dataset crawl)</h4><div class="chat-drug-img-grid">${figures.join(
    ""
  )}</div></div>`;
}

function buildRetrievalConfidenceHtml(rc) {
  // Khong hien thong tin debug retrieval cho end-user.
  return "";
}

function buildSourcesFooter(data) {
  // Khong hien danh sach nguon debug cho end-user.
  return "";
}

function persistAssistantBubbleHtml(innerHtml) {
  const t = getActiveThread();
  if (!t) return;
  t.messages.push({ role: "assistant", html: innerHtml });
  if (t.messages.length > MAX_CHAT_ENTRIES) {
    t.messages = t.messages.slice(-MAX_CHAT_ENTRIES);
  }
  t.updatedAt = Date.now();
  saveThreadsState();
}

function ensureAnswerRow() {
  const row = document.createElement("div");
  row.className = "chat-row chat-row--assistant";
  row.innerHTML = `<div class="chat-row-flex"><span class="chat-avatar" aria-hidden="true">NV</span><div class="chat-bubble chat-bubble--assistant"><div class="chat-bubble-inner"><div class="chat-answer chat-answer--streaming"></div></div></div></div>`;
  $("chatMessages").appendChild(row);
  return row;
}

async function sendAgentQuery() {
  const base = defaultApiBase().replace(/\/$/, "");
  const ta = $("question");
  const message = ta.value.trim();
  const btn = $("sendBtn");

  if (!message) {
    ta.focus();
    return;
  }

  const thread = getActiveThread();
  if (thread) maybeAutoTitle(thread, "user", message);

  appendChatBubble("user", `<div class="chat-bubble-inner">${escapeHtml(message).replace(/\n/g, "<br>")}</div>`, {
    persist: true,
  });
  updateThreadHeader();

  ta.value = "";
  ta.style.height = "auto";
  btn.disabled = true;

  const workRow = document.createElement("div");
  workRow.className = "chat-row chat-row--stream-work";
  workRow.innerHTML = `<div class="chat-stream-work"><span class="chat-stream-work-label">Suy luận &amp; công cụ</span><pre class="chat-stream-reasoning" aria-live="polite"></pre><div class="chat-stream-tools"></div></div>`;
  $("chatMessages").appendChild(workRow);
  const workShell = workRow.querySelector(".chat-stream-work");
  const pre = workRow.querySelector(".chat-stream-reasoning");
  const toolsEl = workRow.querySelector(".chat-stream-tools");

  let answerRow = null;
  let plainAnswer = "";
  let workRemoved = false;

  function removeWorkSoon() {
    if (workRemoved || !workShell) return;
    workRemoved = true;
    workShell.classList.add("is-leaving");
    setTimeout(() => {
      workRow.remove();
    }, 230);
  }

  try {
    // Get selected backend and query mode from UI
    const backendSelect = $("backendSelect");
    const selectedBackend = backendSelect ? backendSelect.value : "auto";
    
    const queryModeSelect = $("queryModeSelect");
    const queryMode = queryModeSelect ? queryModeSelect.value : "agent";
    
    // Handle Neo4j Direct mode (non-streaming, no LLM)
    if (queryMode === "neo4j-direct") {
      const directPath = "/api/langchain-graph-query/direct";
      const r = window.DATNAuth?.authApiFetch
        ? await window.DATNAuth.authApiFetch(directPath, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message }),
          })
        : await fetchWithRetry(`${base}${directPath}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message }),
          });
      
      if (!r.ok) {
        const errText = await r.text();
        workRow.remove();
        appendChatBubble("assistant", `<div class="chat-bubble-inner chat-error"><p>Lỗi: ${escapeHtml(errText)}</p></div>`, {
          persist: true,
        });
        return;
      }
      
      const data = await r.json();
      workRow.remove();
      
      // Format the raw context with sources
      let html = `<div class="chat-bubble-inner">`;
      html += `<div class="chat-answer">`;
      html += `<pre class="chat-raw-context" style="white-space: pre-wrap; font-family: inherit; background: rgba(128,128,128,0.08); padding: 12px; border-radius: 8px; font-size: 14px; line-height: 1.6;">${escapeHtml(data.answer)}</pre>`;
      html += `</div>`;
      
      // Add sources if available
      if (data.sources && data.sources.length > 0) {
        html += `<div class="chat-sources" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(128,128,128,0.15);">`;
        html += `<strong style="font-size: 12px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.3px;">Nguồn:</strong>`;
        html += `<ul style="margin: 8px 0 0 0; padding-left: 18px; font-size: 13px;">`;
        for (const s of data.sources.slice(0, 6)) {
          html += `<li style="margin-bottom: 4px;">${escapeHtml(s.title || "Unknown")} <span style="color: var(--muted);">(${escapeHtml(s.source || "")})</span></li>`;
        }
        html += `</ul></div>`;
      }
      
      html += `</div>`;
      
      appendChatBubble("assistant", html, { persist: true });
      renderThreadList();
      return;
    }
    
    // Default: Agent mode with streaming
    const payload = {
      message,
      strategy: "auto",
      use_react: true,
      backend: selectedBackend,  // 'auto', 'ollama', 'openrouter'
    };
    const streamPath = "/api/agent-query/stream";
    const r = window.DATNAuth?.authApiFetch
      ? await window.DATNAuth.authApiFetch(streamPath, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })
      : await fetchWithRetry(`${base}${streamPath}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

    if (!r.ok) {
      const errText = await r.text();
      let detail = errText;
      try {
        const j = JSON.parse(errText);
        detail = j.detail ?? j.message ?? errText;
      } catch {
        /* ignore */
      }
      workRow.remove();
      const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
      appendChatBubble("assistant", `<div class="chat-bubble-inner chat-error"><p>${escapeHtml(msg)}</p></div>`, {
        persist: true,
      });
      return;
    }

    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += dec.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        let evt;
        try {
          evt = JSON.parse(line);
        } catch {
          continue;
        }
        const ev = evt.event;
        if (ev === "step") {
          pre.textContent = "";
        } else if (ev === "reasoning_delta") {
          pre.textContent += evt.text ?? "";
          scrollChatToBottom();
        } else if (ev === "parse_retry") {
          toolsEl.insertAdjacentHTML(
            "beforeend",
            `<div class="chat-stream-tool chat-stream-tool--muted">Sửa định dạng (lần ${escapeHtml(String(evt.attempt ?? ""))})…</div>`
          );
          pre.textContent = "";
        } else if (ev === "tool") {
          const inp = escapeHtml((evt.input || "").slice(0, CONFIG.MAX_PREVIEW_CHARS));
          toolsEl.insertAdjacentHTML(
            "beforeend",
            `<div class="chat-stream-tool"><strong>Tool</strong> ${escapeHtml(evt.name || "")} · <code>${inp}</code></div>`
          );
          scrollChatToBottom();
        } else if (ev === "tool_done") {
          toolsEl.insertAdjacentHTML(
            "beforeend",
            `<div class="chat-stream-tool chat-stream-tool--ok">Đã nhận kết quả (${evt.observation_chars ?? 0} ký tự)</div>`
          );
          scrollChatToBottom();
        } else if (ev === "answer_start") {
          removeWorkSoon();
          answerRow = ensureAnswerRow();
          plainAnswer = "";
        } else if (ev === "answer_delta") {
          if (!answerRow) answerRow = ensureAnswerRow();
          plainAnswer += evt.text ?? "";
          const el = answerRow.querySelector(".chat-answer--streaming");
          if (el) el.textContent = plainAnswer;
          scrollChatToBottom();
        } else if (ev === "error") {
          toolsEl.insertAdjacentHTML(
            "beforeend",
            `<div class="chat-stream-tool chat-stream-tool--err">${escapeHtml(evt.message || "Lỗi")}</div>`
          );
        } else if (ev === "done") {
          if (!workRemoved && workRow.parentNode) removeWorkSoon();
          const ans = evt.answer ?? "";
          const innerHtml = `<div class="chat-bubble-inner"><div class="chat-answer">${formatAnswerBody(ans)}</div>${buildDrugImagesHtml(evt.drug_images)}${buildRetrievalConfidenceHtml(evt.retrieval_confidence)}${buildSourcesFooter(evt)}</div>`;
          if (answerRow) {
            const bubble = answerRow.querySelector(".chat-bubble--assistant");
            if (bubble) bubble.innerHTML = innerHtml;
            persistAssistantBubbleHtml(innerHtml);
          } else {
            if (workRow.parentNode) workRow.remove();
            appendChatBubble("assistant", innerHtml, { persist: true });
          }
          renderThreadList();
        }
      }
    }
  } catch (e) {
    if (workRow.parentNode) workRow.remove();
    appendChatBubble("assistant", `<div class="chat-bubble-inner chat-error"><p>${escapeHtml(e.message || String(e))}</p></div>`, {
      persist: true,
    });
  } finally {
    btn.disabled = false;
    scrollChatToBottom();
    $("question").focus();
  }
}

function formatAnswerBody(text) {
  const t = String(text || "");
  if (!t.trim()) return "<p class=\"chat-muted\">(Không có nội dung)</p>";
  const toInlineHtml = (input) =>
    escapeHtml(input)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>");
  const paras = t.split(/\n{2,}/).map((p) => `<p>${toInlineHtml(p).replace(/\n/g, "<br>")}</p>`);
  return paras.join("");
}

function setupMessengerInput() {
  const ta = $("question");
  if (!ta) return;
  const grow = () => {
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  };
  ta.addEventListener("input", grow);
  grow();
}

/* ——— Reminders (một lần · hằng ngày · cách N giờ) ——— */

function normalizeTimeSlot(s) {
  const m = String(s || "")
    .trim()
    .match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const h = parseInt(m[1], 10);
  const min = parseInt(m[2], 10);
  if (h < 0 || h > 23 || min < 0 || min > 59) return null;
  return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}

function parseDailyTimes(str) {
  const parts = String(str || "").split(/[,;]+/);
  const out = [];
  const seen = new Set();
  for (const p of parts) {
    const slot = normalizeTimeSlot(p);
    if (slot && !seen.has(slot)) {
      seen.add(slot);
      out.push(slot);
    }
  }
  return out.sort();
}

function dateKeyLocal(d) {
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const da = String(d.getDate()).padStart(2, "0");
  return `${y}-${mo}-${da}`;
}

function clockKeyLocal(d) {
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function computeNextIntervalDue(startIso, intervalHours) {
  const h = intervalHours * 3600000;
  let t = new Date(startIso).getTime();
  const now = Date.now();
  if (Number.isNaN(t)) t = now;
  while (t <= now) t += h;
  return new Date(t).toISOString();
}

function normalizeStoredReminder(x) {
  if (!x || typeof x.id !== "string" || typeof x.text !== "string") return null;
  if (x.kind === "daily" && Array.isArray(x.times) && x.times.length) {
    const parsed = parseDailyTimes(x.times.join(","));
    const times = parsed.length ? parsed : x.times.map((t) => normalizeTimeSlot(String(t))).filter(Boolean);
    if (!times.length) return null;
    return {
      id: x.id,
      text: x.text,
      kind: "daily",
      times,
      lastFired: typeof x.lastFired === "object" && x.lastFired ? x.lastFired : {},
    };
  }
  if (x.kind === "interval" && typeof x.intervalHours === "number" && x.intervalHours > 0 && typeof x.nextDueIso === "string") {
    return {
      id: x.id,
      text: x.text,
      kind: "interval",
      intervalHours: Math.min(72, Math.max(1, Math.floor(x.intervalHours))),
      nextDueIso: x.nextDueIso,
    };
  }
  if (typeof x.at === "string") {
    return {
      id: x.id,
      text: x.text,
      kind: "once",
      at: x.at,
      notified: Boolean(x.notified),
    };
  }
  return null;
}

function loadReminders() {
  try {
    let raw = localStorage.getItem(STORAGE_REMINDERS);
    if (!raw) {
      raw = localStorage.getItem(STORAGE_REMINDERS_V1);
    }
    if (!raw) {
      reminders = [];
      return;
    }
    const arr = JSON.parse(raw);
    reminders = Array.isArray(arr)
      ? arr.map(normalizeStoredReminder).filter(Boolean).slice(-MAX_REMINDERS)
      : [];
    saveReminders();
  } catch {
    reminders = [];
  }
}

function saveReminders() {
  try {
    localStorage.setItem(STORAGE_REMINDERS, JSON.stringify(reminders));
  } catch {
    while (reminders.length > 1) {
      reminders.shift();
      try {
        localStorage.setItem(STORAGE_REMINDERS, JSON.stringify(reminders));
        return;
      } catch {
        /* continue */
      }
    }
  }
}

function formatReminderWhen(iso) {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function reminderSummaryLine(r) {
  if (r.kind === "daily") {
    return `Mỗi ngày: ${r.times.join(", ")}`;
  }
  if (r.kind === "interval") {
    return `Mỗi ${r.intervalHours} giờ · lần tới: ${formatReminderWhen(r.nextDueIso)}`;
  }
  return formatReminderWhen(r.at);
}

function sortRemindersForDisplay(list) {
  return [...list].sort((a, b) => {
    const ka = a.kind === "once" ? a.at : a.kind === "interval" ? a.nextDueIso : a.times?.[0] || "";
    const kb = b.kind === "once" ? b.at : b.kind === "interval" ? b.nextDueIso : b.times?.[0] || "";
    return String(ka).localeCompare(String(kb));
  });
}

function renderRemindersPanel() {
  const panel = $("remindersPanel");
  if (!panel || panel.classList.contains("hidden")) return;
  if (!reminders.length) {
    panel.innerHTML = "<p class=\"chat-reminders-empty\">Chưa có lịch. Dùng «Đặt lịch nhắc».</p>";
    return;
  }
  const sorted = sortRemindersForDisplay(reminders);
  panel.innerHTML = sorted
    .map((r) => {
      const kindLabel =
        r.kind === "daily" ? "Hằng ngày" : r.kind === "interval" ? "Cách N giờ" : "Một lần";
      return `<div class="chat-reminder-row" data-id="${escapeAttr(r.id)}">
          <div class="chat-reminder-text">${escapeHtml(r.text)}</div>
          <div class="chat-reminder-meta"><span class="chat-reminder-kind">${escapeHtml(kindLabel)}</span> · ${escapeHtml(
            reminderSummaryLine(r)
          )}</div>
          <button type="button" class="chat-reminder-remove" data-remove="${escapeAttr(r.id)}">Xóa</button>
        </div>`;
    })
    .join("");
  panel.querySelectorAll("[data-remove]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-remove");
      reminders = reminders.filter((x) => x.id !== id);
      saveReminders();
      renderRemindersPanel();
    });
  });
}

function showToast(text) {
  const t = $("reminderToast");
  if (!t) return;
  t.textContent = text;
  t.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => t.classList.add("hidden"), 8000);
}

function tryNotify(title, body) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  try {
    new Notification(title, { body, tag: "datn-reminder" });
  } catch {
    /* ignore */
  }
}

function syncReminderKindUI() {
  const kind = document.querySelector('input[name="reminderKind"]:checked')?.value || "once";
  const onceEl = $("reminderFieldsOnce");
  const dailyEl = $("reminderFieldsDaily");
  const intEl = $("reminderFieldsInterval");
  const when = $("reminderWhen");
  if (onceEl) onceEl.classList.toggle("hidden", kind !== "once");
  if (dailyEl) dailyEl.classList.toggle("hidden", kind !== "daily");
  if (intEl) intEl.classList.toggle("hidden", kind !== "interval");
  if (when) when.required = kind === "once";
}

function checkDueReminders() {
  const now = Date.now();
  const maxAgeMs = 48 * 3600000;
  const nowDate = new Date();
  const todayStr = dateKeyLocal(nowDate);
  const hm = clockKeyLocal(nowDate);
  let changed = false;

  for (const r of reminders) {
    if (r.kind === "once") {
      const t = new Date(r.at).getTime();
      if (Number.isNaN(t) || r.notified) continue;
      if (t <= now) {
        r.notified = true;
        changed = true;
        const age = now - t;
        if (age < maxAgeMs) {
          showToast(`Nhắc nhở: ${r.text}`);
          tryNotify("Nhắc nhở y tế", r.text);
        }
      }
      continue;
    }

    if (r.kind === "daily") {
      if (!r.lastFired || typeof r.lastFired !== "object") r.lastFired = {};
      for (const slot of r.times) {
        if (slot !== hm) continue;
        if (r.lastFired[slot] === todayStr) continue;
        r.lastFired[slot] = todayStr;
        changed = true;
        showToast(`Nhắc uống thuốc: ${r.text} (${slot})`);
        tryNotify("Nhắc uống thuốc", `${r.text} — ${slot}`);
      }
      continue;
    }

    if (r.kind === "interval") {
      let due = new Date(r.nextDueIso).getTime();
      if (Number.isNaN(due)) continue;
      if (due > now) continue;
      const h = r.intervalHours * 3600000;
      showToast(`Nhắc nhở: ${r.text}`);
      tryNotify("Nhắc nhở y tế", r.text);
      while (due <= now) due += h;
      r.nextDueIso = new Date(due).toISOString();
      changed = true;
    }
  }

  if (changed) saveReminders();
}

function openReminderDialog() {
  const dlg = $("reminderDialog");
  const when = $("reminderWhen");
  const text = $("reminderText");
  const dailyTimes = $("reminderDailyTimes");
  const intH = $("reminderIntervalHours");
  const intStart = $("reminderIntervalStart");
  if (!dlg || !when || !text) return;
  text.value = "";
  const onceRadio = document.querySelector('input[name="reminderKind"][value="once"]');
  if (onceRadio) onceRadio.checked = true;
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  const localSlice = d.toISOString().slice(0, 16);
  when.value = localSlice;
  if (dailyTimes) dailyTimes.value = "8:00, 20:00";
  if (intH) intH.value = "6";
  if (intStart) intStart.value = localSlice;
  syncReminderKindUI();
  if (typeof dlg.showModal === "function") dlg.showModal();
  else text.focus();
}

function closeReminderDialog() {
  const dlg = $("reminderDialog");
  if (dlg && typeof dlg.close === "function") dlg.close();
}

function submitReminder(e) {
  e.preventDefault();
  const text = $("reminderText")?.value.trim();
  const kind = document.querySelector('input[name="reminderKind"]:checked')?.value || "once";
  if (!text) return;

  if (kind === "once") {
    const when = $("reminderWhen")?.value;
    if (!when) return;
    const iso = new Date(when).toISOString();
    reminders.push({ id: newId("r"), text, kind: "once", at: iso, notified: false });
  } else if (kind === "daily") {
    const times = parseDailyTimes($("reminderDailyTimes")?.value || "");
    if (!times.length) {
      alert("Nhập ít nhất một giờ hợp lệ (vd. 8:00, 21:00).");
      return;
    }
    reminders.push({ id: newId("r"), text, kind: "daily", times, lastFired: {} });
  } else if (kind === "interval") {
    const rawH = $("reminderIntervalHours")?.value;
    const intervalHours = Math.min(72, Math.max(1, parseInt(String(rawH), 10) || 6));
    const startVal = $("reminderIntervalStart")?.value;
    const startIso = startVal ? new Date(startVal).toISOString() : new Date().toISOString();
    const nextDueIso = computeNextIntervalDue(startIso, intervalHours);
    reminders.push({ id: newId("r"), text, kind: "interval", intervalHours, nextDueIso });
  }

  if (reminders.length > MAX_REMINDERS) reminders = reminders.slice(-MAX_REMINDERS);
  saveReminders();
  closeReminderDialog();
  const panel = $("remindersPanel");
  if (panel && !panel.classList.contains("hidden")) renderRemindersPanel();

  const summary =
    kind === "once"
      ? formatReminderWhen(reminders[reminders.length - 1].at)
      : kind === "daily"
        ? `mỗi ngày ${reminders[reminders.length - 1].times.join(", ")}`
        : reminderSummaryLine(reminders[reminders.length - 1]);

  appendChatBubble(
    "assistant",
    `<div class="chat-bubble-inner"><p class="chat-muted"><strong>Lịch nhắc:</strong> Đã lưu — ${escapeHtml(text)} · ${escapeHtml(
      summary
    )}</p></div>`,
    { persist: true }
  );
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission().catch(() => {});
  }
}

function toggleRemindersPanel() {
  const panel = $("remindersPanel");
  const btn = $("toggleRemindersPanelBtn");
  if (!panel) return;
  const hidden = panel.classList.toggle("hidden");
  if (btn) btn.setAttribute("aria-expanded", hidden ? "false" : "true");
  if (!hidden) renderRemindersPanel();
}

/* ——— Sidebar collapse ——— */

function setupSidebarToggle() {
  const btn = $("sidebarToggle");
  const layout = document.querySelector(".chat-page-layout");
  if (!btn || !layout) return;
  btn.addEventListener("click", () => {
    const collapsed = layout.classList.toggle("chat-sidebar-collapsed");
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    btn.setAttribute("aria-label", collapsed ? "Mở sidebar cuộc trò chuyện" : "Thu gọn sidebar");
    btn.title = collapsed ? "Mở sidebar" : "Thu gọn sidebar";
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  if (window.DATNAuth?.bindAuthUi) window.DATNAuth.bindAuthUi();
  if (document.body?.dataset?.protected === "true" && window.DATNAuth?.ensureProtectedPage) {
    await window.DATNAuth.ensureProtectedPage();
  }
  applyTheme();
  void runReadinessBanner();
  loadThreadsState();
  loadReminders();
  setupMessengerInput();
  renderChatFromStorage();
  renderThreadList();
  updateThreadHeader();
  setupSidebarToggle();

  $("sendBtn").addEventListener("click", sendAgentQuery);
  $("newThreadBtn")?.addEventListener("click", createNewThread);
  $("deleteThreadBtn")?.addEventListener("click", deleteCurrentThread);
  $("themeToggle").addEventListener("click", toggleTheme);
  $("question").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendAgentQuery();
    }
  });

  $("openReminderDialogBtn")?.addEventListener("click", openReminderDialog);
  $("reminderCancelBtn")?.addEventListener("click", closeReminderDialog);
  $("toggleRemindersPanelBtn")?.addEventListener("click", toggleRemindersPanel);
  $("reminderForm")?.addEventListener("submit", submitReminder);
  document.querySelectorAll('input[name="reminderKind"]').forEach((el) => {
    el.addEventListener("change", syncReminderKindUI);
  });
  syncReminderKindUI();

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!localStorage.getItem(STORAGE_THEME)) applyTheme();
  });

  // Backend selector initialization
  function initBackendSelector() {
    const backendSelect = $("backendSelect");
    if (!backendSelect) return;
    
    // Load saved preference
    const savedBackend = localStorage.getItem(STORAGE_BACKEND) || "auto";
    backendSelect.value = savedBackend;
    
    // Save on change
    backendSelect.addEventListener("change", () => {
      localStorage.setItem(STORAGE_BACKEND, backendSelect.value);
    });
  }
  initBackendSelector();

  // Query mode selector initialization
  function initQueryModeSelector() {
    const queryModeSelect = $("queryModeSelect");
    if (!queryModeSelect) return;
    
    // Load saved preference
    const savedMode = localStorage.getItem(STORAGE_QUERY_MODE) || "agent";
    queryModeSelect.value = savedMode;
    
    // Save on change and update UI hint
    queryModeSelect.addEventListener("change", () => {
      localStorage.setItem(STORAGE_QUERY_MODE, queryModeSelect.value);
      
      // Show/hide backend selector based on mode
      const backendSelect = $("backendSelect");
      const backendLabel = document.querySelector('label[for="backendSelect"]');
      if (backendSelect && backendLabel) {
        const isDirect = queryModeSelect.value === "neo4j-direct";
        backendSelect.disabled = isDirect;
        backendLabel.style.opacity = isDirect ? "0.5" : "1";
      }
    });
    
    // Trigger initial state
    queryModeSelect.dispatchEvent(new Event("change"));
  }
  initQueryModeSelector();

  setInterval(checkDueReminders, 30_000);
  checkDueReminders();
});
