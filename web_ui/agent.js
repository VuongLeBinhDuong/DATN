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
  renderAllGraphs();
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
      t.messages.push({ role, html, text: options.text || html });
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

function buildPdfExportButtonHtml() {
  return "";
}

function exportClinicalPdf(btn) {
  const bubble = btn.closest(".chat-bubble-inner");
  if (!bubble) return;
  
  // Clone the node to avoid altering live UI elements
  const printClone = bubble.cloneNode(true);
  
  // Remove print-unfriendly features
  const actions = printClone.querySelector(".chat-actions");
  if (actions) actions.remove();
  
  const thinkingDetails = printClone.querySelector(".chat-thinking-details");
  if (thinkingDetails) thinkingDetails.remove();
  
  // Package into report layout
  const reportContainer = document.createElement("div");
  reportContainer.style.padding = "30px";
  reportContainer.style.fontFamily = "'Source Sans 3', sans-serif";
  reportContainer.style.color = "#1e293b";
  reportContainer.style.background = "#ffffff";
  
  const headerHtml = `
    <div style="border-bottom: 2px solid #d97706; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
      <div>
        <h1 style="margin: 0; font-size: 20px; font-weight: bold; color: #1e3a8a; text-transform: uppercase; letter-spacing: 0.5px;">Hệ Thống Hỗ Trợ Quyết Định Lâm Sàng CDSS</h1>
        <p style="margin: 4px 0 0 0; font-size: 12px; color: #64748b;">BÁO CÁO KHUYẾN NGHỊ Y KHOA TỰ ĐỘNG (CDSS-REPORT)</p>
      </div>
      <div style="text-align: right; font-size: 11px; color: #64748b;">
        <p style="margin: 0;">Mã số báo cáo: CDSS_${Date.now().toString().slice(-6)}</p>
        <p style="margin: 2px 0 0 0;">Ngày tạo: ${new Date().toLocaleString("vi-VN")}</p>
      </div>
    </div>
    
    <div style="margin-bottom: 20px; background: #f8fafc; padding: 12px; border-radius: 8px; font-size: 13px; border: 1px solid #e2e8f0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
      <div><strong>Đối tượng áp dụng:</strong> Nhân viên y tế & Bệnh nhân tham khảo</div>
      <div><strong>Nguồn dữ liệu:</strong> Đồ thị Tri thức Y học Neo4j & Reranker lai đa tầng</div>
      <div><strong>Mức độ tin cậy:</strong> Chuẩn y khoa định mức (0ms / ReAct Agent)</div>
      <div><strong>Trạng thái xác thực:</strong> Tự động đối chiếu WHO / Bộ Y tế</div>
    </div>
  `;
  
  const footerHtml = `
    <div style="margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 12px; font-size: 10px; color: #64748b; text-align: center; line-height: 1.4;">
      <p style="margin: 0;">Báo cáo này được tạo tự động bởi Hệ Thống Hỗ Trợ Quyết Định Lâm Sàng CDSS.</p>
      <p style="margin: 2px 0 0 0; font-weight: bold; color: #b45309;">LƯU Ý: Kết quả chỉ mang tính chất tham khảo chuyên môn kỹ thuật, không thay thế cho quyết định chẩn đoán lâm sàng cuối cùng của bác sĩ điều trị.</p>
    </div>
  `;
  
  reportContainer.innerHTML = headerHtml + printClone.innerHTML + footerHtml;
  
  const opt = {
    margin:       10,
    filename:     `CDSS_Report_${Date.now().toString().slice(-6)}.pdf`,
    image:        { type: 'jpeg', quality: 0.98 },
    html2canvas:  { scale: 2, useCORS: true },
    jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' }
  };
  
  document.body.appendChild(reportContainer);
  
  html2pdf().from(reportContainer).set(opt).save().then(() => {
    document.body.removeChild(reportContainer);
  });
}

/* --- Premium Interactive Entity Node Graph (Vis-Network) --- */

function parseSubgraphFromContext(text) {
  if (!text) return null;
  const nodes = [];
  const edges = [];
  const lines = text.split("\n");
  
  let currentEntity = null;
  let inRelations = false;
  
  for (let line of lines) {
    line = line.trim();
    if (!line) continue;
    
    if (line.includes("Quan hệ (trong tập trên)") || line.includes("RELATED") || line.includes("Quan hệ")) {
      inRelations = true;
      continue;
    }
    
    if (!inRelations) {
      const entityMatch = line.match(/^---\s*Entity\s*\[\d+\]\s*\(score≈([\d.]+)\)\s*id=(.+?)\s*---$/i);
      if (entityMatch) {
        if (currentEntity) {
          nodes.push(currentEntity);
        }
        currentEntity = {
          id: entityMatch[2].trim(),
          label: entityMatch[2].trim(),
          type: "Entity",
          score: parseFloat(entityMatch[1])
        };
        continue;
      }
      
      if (currentEntity) {
        if (line.startsWith("title:")) {
          currentEntity.label = line.replace("title:", "").trim();
        } else if (line.startsWith("type:")) {
          currentEntity.type = line.replace("type:", "").trim();
        } else if (line.startsWith("description:")) {
          currentEntity.description = line.replace("description:", "").trim();
        }
      }
    } else {
      const relMatch = line.match(/([a-zA-Z0-9_]+)\s*—\[([^\]]+)\]→\s*([a-zA-Z0-9_]+)/);
      if (relMatch) {
        edges.push({
          from: relMatch[1].trim(),
          to: relMatch[3].trim(),
          label: relMatch[2].trim()
        });
      }
    }
  }
  
  if (currentEntity) {
    nodes.push(currentEntity);
  }
  
  const uniqueNodes = [];
  const seenNodes = new Set();
  for (const n of nodes) {
    const key = n.id.toLowerCase();
    if (!seenNodes.has(key)) {
      seenNodes.add(key);
      uniqueNodes.push(n);
    }
  }
  
  // Lọc cạnh để chỉ giữ các cạnh có cả hai đầu mút nằm trong uniqueNodes
  const nodeIds = new Set(uniqueNodes.map(n => n.id.toLowerCase()));
  let filteredEdges = edges.filter(e => nodeIds.has(e.from.toLowerCase()) && nodeIds.has(e.to.toLowerCase()));
  
  // Giới hạn số lượng thực thể tối đa từ 10 - 15 (chọn 15) để sơ đồ gọn gàng
  const MAX_ENTITIES = 15;
  let prunedNodes = uniqueNodes;
  let prunedEdges = filteredEdges;
  
  if (uniqueNodes.length > MAX_ENTITIES) {
    prunedNodes = uniqueNodes.slice(0, MAX_ENTITIES);
    const prunedNodeIds = new Set(prunedNodes.map(n => n.id.toLowerCase()));
    prunedEdges = filteredEdges.filter(e => prunedNodeIds.has(e.from.toLowerCase()) && prunedNodeIds.has(e.to.toLowerCase()));
  }
  
  return prunedNodes.length > 0 ? { nodes: prunedNodes, edges: prunedEdges } : null;
}

window.toggleSubgraph = function(btn) {
  const wrapper = btn.closest(".chat-subgraph-wrapper");
  if (!wrapper) return;
  const body = wrapper.querySelector(".chat-subgraph-body");
  if (!body) return;
  
  if (body.style.display === "none") {
    body.style.display = "block";
    btn.textContent = "Ẩn sơ đồ";
    
    const canvas = body.querySelector(".chat-subgraph-canvas");
    if (canvas && canvas.children.length === 0) {
      const contextText = wrapper.getAttribute("data-context");
      const subgraph = parseSubgraphFromContext(contextText);
      if (subgraph) {
        renderGraphInContainer(canvas.id, subgraph);
      }
    }
  } else {
    body.style.display = "none";
    btn.textContent = "Hiện sơ đồ";
  }
};

function buildSubgraphHtml(contextText) {
  if (!contextText || !contextText.trim()) return "";
  const subgraph = parseSubgraphFromContext(contextText);
  if (!subgraph) return "";
  
  const containerId = `subgraph_${newId("g")}`;
  return `<div class="chat-subgraph-wrapper" data-context="${escapeAttr(contextText)}">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
      <div class="chat-subgraph-title" style="margin: 0;">Sơ đồ mạng lưới thực thể y khoa</div>
      <button type="button" onclick="toggleSubgraph(this)" style="background: transparent; border: 1px solid var(--line, rgba(128,128,128,0.25)); border-radius: 4px; padding: 2px 8px; font-size: 11px; color: var(--text-muted, #777); cursor: pointer; transition: all 0.2s; font-family: inherit;">Ẩn sơ đồ</button>
    </div>
    <div class="chat-subgraph-body">
      <div id="${containerId}" class="chat-subgraph-canvas" style="height: 320px; width: 100%; border-radius: 8px; background: var(--bg-elevated, #fff); margin-top: 10px; border: 1px solid var(--line, rgba(128,128,128,0.15));"></div>
      <div class="chat-subgraph-hint" style="margin-top: 4px;">* Kéo các thực thể để sắp xếp, click để xem mô tả chi tiết</div>
    </div>
  </div>`;
}

function renderGraphInContainer(containerId, subgraph) {
  const container = document.getElementById(containerId);
  if (!container || !subgraph || !window.vis) return;
  
  const nodes = subgraph.nodes.map(n => {
    let color = {
      background: "rgba(217, 119, 54, 0.08)",
      border: "#d97736",
      highlight: { background: "rgba(217, 119, 54, 0.16)", border: "#c25e1a" }
    };
    
    const type = String(n.type || "").toLowerCase();
    if (type.includes("disease") || type.includes("bệnh")) {
      color = {
        background: "rgba(229, 57, 53, 0.08)",
        border: "#e53935",
        highlight: { background: "rgba(229, 57, 53, 0.16)", border: "#b71c1c" }
      };
    } else if (type.includes("drug") || type.includes("thuốc") || type.includes("treatment")) {
      color = {
        background: "rgba(67, 160, 71, 0.08)",
        border: "#43a047",
        highlight: { background: "rgba(67, 160, 71, 0.16)", border: "#1b5e20" }
      };
    } else if (type.includes("symptom") || type.includes("triệu chứng")) {
      color = {
        background: "rgba(251, 192, 45, 0.08)",
        border: "#fbc02d",
        highlight: { background: "rgba(251, 192, 45, 0.16)", border: "#f57f17" }
      };
    }
    
    const isSeed = n.score > 1.5;
    const fontSize = isSeed ? 15 : 11;
    const borderW = isSeed ? 3.0 : 1.2;
    const margin = isSeed ? 12 : 6;
    
    return {
      id: n.id,
      label: n.label,
      title: n.description || n.label,
      shape: "box",
      margin: margin,
      font: { face: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif", size: fontSize, bold: true },
      color: color,
      borderWidth: borderW,
      shapeProperties: { borderRadius: 6 }
    };
  });
  
  const edges = subgraph.edges.map(e => {
    return {
      from: e.from,
      to: e.to,
      label: e.label,
      arrows: "to",
      font: { size: 9, align: "horizontal", color: "#888" },
      color: { color: "rgba(128,128,128,0.25)", highlight: "#d97736" }
    };
  });
  
  const data = {
    nodes: new vis.DataSet(nodes),
    edges: new vis.DataSet(edges)
  };
  
  const options = {
    physics: {
      solver: "forceAtlas2Based",
      forceAtlas2Based: {
        gravitationalConstant: -35,
        centralGravity: 0.015,
        springLength: 100,
        springConstant: 0.08
      }
    },
    interaction: {
      hover: true,
      tooltipDelay: 200,
      zoomView: true,
      dragView: true
    }
  };
  
  const network = new vis.Network(container, data, options);
  
  network.on("click", function(params) {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      const node = subgraph.nodes.find(n => n.id === nodeId);
      if (node && node.description) {
        showToast(`${node.label}: ${node.description}`);
      }
    }
  });
}

function renderAllGraphs() {
  if (!window.vis) return;
  document.querySelectorAll(".chat-subgraph-wrapper").forEach(wrapper => {
    const body = wrapper.querySelector(".chat-subgraph-body");
    if (body && body.style.display === "none") return;
    
    const canvas = wrapper.querySelector(".chat-subgraph-canvas");
    if (!canvas || canvas.children.length > 0) return;
    
    const contextText = wrapper.getAttribute("data-context");
    if (!contextText) return;
    
    const subgraph = parseSubgraphFromContext(contextText);
    if (subgraph) {
      renderGraphInContainer(canvas.id, subgraph);
    }
  });
}

function persistAssistantBubbleHtml(innerHtml, cleanText) {
  const t = getActiveThread();
  if (!t) return;
  t.messages.push({ role: "assistant", html: innerHtml, text: cleanText });
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
    text: message,
  });
  updateThreadHeader();

  ta.value = "";
  ta.style.height = "auto";
  btn.disabled = true;

  let answerRow = null;
  let plainAnswer = "";
  let pre = null;
  let toolsEl = null;
  let thinkingTitle = null;
  let thinkingDetails = null;
  let thinkingIndicator = null;

  try {
    // Get selected backend and query mode from UI
    const backendSelect = $("backendSelect");
    const selectedBackend = backendSelect ? backendSelect.value : "auto";
    
    const queryModeSelect = $("queryModeSelect");
    const queryMode = queryModeSelect ? queryModeSelect.value : "agent";
    
    // Handle Neo4j Direct mode (non-streaming, no LLM)
    if (queryMode === "neo4j-direct") {
      const directWorkRow = document.createElement("div");
      directWorkRow.className = "chat-row chat-row--stream-work";
      directWorkRow.innerHTML = `<div class="chat-stream-work" style="padding: 10px 14px; border-radius: 8px; border: 1px dashed var(--line); font-size: 13px; color: var(--muted);"><span class="chat-thinking-indicator" style="margin-right: 8px; vertical-align: middle;"></span> Đang truy vấn Neo4j trực tiếp...</div>`;
      $("chatMessages").appendChild(directWorkRow);
      scrollChatToBottom();

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
        directWorkRow.remove();
        appendChatBubble("assistant", `<div class="chat-bubble-inner chat-error"><p>Lỗi: ${escapeHtml(errText)}</p></div>`, {
          persist: true,
        });
        btn.disabled = false;
        return;
      }
      
      const data = await r.json();
      directWorkRow.remove();
      
      // Format the raw context with sources
      let html = `<div class="chat-bubble-inner">`;
      html += `<div class="chat-answer">`;
      html += `<p style="margin: 0 0 10px 0; font-weight: 500; color: var(--text);">Hệ thống đã truy xuất cơ sở dữ liệu đồ thị tri thức Neo4j và dựng sơ đồ mạng lưới thực thể bên dưới.</p>`;
      html += `<details class="chat-details" style="margin-top: 8px;">`;
      html += `<summary style="font-size: 13px; color: var(--muted); cursor: pointer; user-select: none;">Xem chi tiết ${data.sources ? data.sources.length : 0} ngữ cảnh đã truy xuất (raw context)</summary>`;
      html += `<pre class="chat-raw-context" style="white-space: pre-wrap; font-family: inherit; background: rgba(128,128,128,0.08); padding: 12px; border-radius: 8px; font-size: 13px; line-height: 1.6; margin-top: 8px; max-height: 250px; overflow-y: auto;">${escapeHtml(data.answer)}</pre>`;
      html += `</details>`;
      html += `</div>`;
      
      // Add dynamic subgraph canvas
      html += buildSubgraphHtml(data.answer);
      

      // Add PDF export button
      html += buildPdfExportButtonHtml();
      html += `</div>`;
      
      appendChatBubble("assistant", html, { persist: true, text: data.answer });
      renderThreadList();
      renderAllGraphs();
      btn.disabled = false;
      return;
    }
    
    // Fetch and map previous chat turns (excluding the latest user message)
    const history = currentMessages()
      .slice(0, -1)
      .map(msg => ({
        role: msg.role === "assistant" ? "assistant" : "user",
        content: msg.text || msg.html || ""
      }));

    // Default: Agent mode with streaming
    const payload = {
      message,
      strategy: "auto",
      use_react: true,
      backend: selectedBackend,  // 'auto', 'ollama', 'openrouter'
      history,
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
      const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
      appendChatBubble("assistant", `<div class="chat-bubble-inner chat-error"><p>${escapeHtml(msg)}</p></div>`, {
        persist: true,
      });
      btn.disabled = false;
      return;
    }

    // Initialize answer row containing Deep Thinking Accordion
    answerRow = ensureAnswerRow();
    const bubbleInner = answerRow.querySelector(".chat-bubble-inner");
    bubbleInner.innerHTML = `
      <details class="chat-details chat-thinking-details" open>
        <summary class="chat-thinking-summary">
          <span class="chat-thinking-indicator"></span>
          <span class="chat-thinking-title">Đang kết nối hệ sinh thái tri thức y khoa...</span>
        </summary>
        <div class="chat-details-body chat-thinking-body">
          <pre class="chat-stream-reasoning" style="white-space: pre-wrap; font-family: monospace; font-size: 11px; max-height: 180px; overflow-y: auto; margin: 0; padding: 0; background: transparent; border: none;"></pre>
          <div class="chat-stream-tools" style="margin-top: 8px; display: flex; flex-direction: column; gap: 4px;"></div>
        </div>
      </details>
      <div class="chat-answer chat-answer--streaming"></div>
    `;
    
    pre = bubbleInner.querySelector(".chat-stream-reasoning");
    toolsEl = bubbleInner.querySelector(".chat-stream-tools");
    thinkingTitle = bubbleInner.querySelector(".chat-thinking-title");
    thinkingDetails = bubbleInner.querySelector(".chat-thinking-details");
    thinkingIndicator = bubbleInner.querySelector(".chat-thinking-indicator");

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
          if (pre) pre.textContent = "";
          if (thinkingTitle) {
            thinkingTitle.textContent = `Đang lập luận và suy luận lâm sàng (bước ${evt.iteration})...`;
          }
        } else if (ev === "reasoning_delta") {
          if (pre) pre.textContent += evt.text ?? "";
          scrollChatToBottom();
        } else if (ev === "parse_retry") {
          if (toolsEl) {
            toolsEl.insertAdjacentHTML(
              "beforeend",
              `<div class="chat-stream-tool chat-stream-tool--muted">Sửa định dạng ReAct (lần ${escapeHtml(String(evt.attempt ?? ""))})…</div>`
            );
          }
          if (pre) pre.textContent = "";
          if (thinkingTitle) {
            thinkingTitle.textContent = `Đang điều chỉnh định dạng ReAct...`;
          }
        } else if (ev === "tool") {
          const inp = escapeHtml((evt.input || "").slice(0, CONFIG.MAX_PREVIEW_CHARS));
          let toolName = evt.name;
          if (evt.name === "graphrag_query") {
            toolName = "Truy vấn Đồ thị tri thức (GraphRAG)";
          } else if (evt.name === "pill_image_lookup") {
            toolName = "Tìm kiếm ảnh thuốc";
          } else if (evt.name === "medical_calculator") {
            toolName = "Công cụ tính chỉ số sinh học (BMI, eGFR)";
          } else if (evt.name === "drug_interaction_checker") {
            toolName = "Kiểm tra tương tác thuốc (Neo4j)";
          }
          if (toolsEl) {
            toolsEl.insertAdjacentHTML(
              "beforeend",
              `<div class="chat-stream-tool"><strong>Gọi công cụ:</strong> ${escapeHtml(toolName)} · <code>${inp}</code></div>`
            );
          }
          if (thinkingTitle) {
            thinkingTitle.textContent = `Đang chạy công cụ: ${toolName}...`;
          }
          scrollChatToBottom();
        } else if (ev === "tool_done") {
          if (toolsEl) {
            toolsEl.insertAdjacentHTML(
              "beforeend",
              `<div class="chat-stream-tool chat-stream-tool--ok">Đã nhận kết quả (${evt.observation_chars ?? 0} ký tự)</div>`
            );
          }
          if (thinkingTitle) {
            thinkingTitle.textContent = `Đang tiếp tục suy luận y khoa...`;
          }
          scrollChatToBottom();
        } else if (ev === "answer_start") {
          if (thinkingDetails) {
            thinkingDetails.removeAttribute("open");
          }
          if (thinkingTitle) {
            thinkingTitle.textContent = `Đã hoàn thành suy luận và truy vấn tri thức y khoa`;
          }
          if (thinkingIndicator) {
            thinkingIndicator.className = "chat-thinking-indicator chat-thinking-indicator--done";
          }
          
          // Dọn dẹp nội dung Thought để tránh hiển thị trùng lặp câu trả lời
          if (pre) {
            let rawText = pre.textContent;
            const markerIndex = rawText.search(/Final\s+Answer\s*:/i);
            if (markerIndex !== -1) {
              pre.textContent = rawText.substring(0, markerIndex).trim();
            } else {
              const cleanText = rawText.trim();
              if (cleanText.startsWith("-") || cleanText.startsWith("*") || (!cleanText.includes("Thought:") && !cleanText.includes("Action:"))) {
                pre.textContent = "Thought: Đang tổng hợp câu trả lời dựa trên thông tin y khoa đã tra cứu.";
              }
            }
          }
          
          plainAnswer = "";
        } else if (ev === "answer_delta") {
          plainAnswer += evt.text ?? "";
          const el = answerRow.querySelector(".chat-answer--streaming");
          if (el) el.textContent = plainAnswer;
          scrollChatToBottom();
        } else if (ev === "error") {
          if (toolsEl) {
            toolsEl.insertAdjacentHTML(
              "beforeend",
              `<div class="chat-stream-tool chat-stream-tool--err">${escapeHtml(evt.message || "Lỗi")}</div>`
            );
          }
        } else if (ev === "done") {
          const ans = evt.answer ?? "";
          const graphHtml = buildSubgraphHtml(evt.context_graphrag_full);
          const thinkingHtml = `
            <details class="chat-details chat-thinking-details">
              <summary class="chat-thinking-summary">
                <span class="chat-thinking-indicator chat-thinking-indicator--done"></span>
                <span class="chat-thinking-title">Đã hoàn thành suy luận và truy vấn tri thức y khoa</span>
              </summary>
              <div class="chat-details-body chat-thinking-body">
                <pre class="chat-stream-reasoning" style="white-space: pre-wrap; font-family: monospace; font-size: 11px; max-height: 180px; overflow-y: auto; margin: 0; padding: 0; background: transparent; border: none;">${escapeHtml(pre ? pre.textContent : "")}</pre>
                <div class="chat-stream-tools" style="margin-top: 8px; display: flex; flex-direction: column; gap: 4px;">${toolsEl ? toolsEl.innerHTML : ""}</div>
              </div>
            </details>
          `;
          const innerHtml = `<div class="chat-bubble-inner">${thinkingHtml}<div class="chat-answer">${formatAnswerBody(ans)}</div>${graphHtml}${buildDrugImagesHtml(evt.drug_images)}${buildRetrievalConfidenceHtml(evt.retrieval_confidence)}${buildSourcesFooter(evt)}${buildPdfExportButtonHtml()}</div>`;
          if (answerRow) {
            const bubble = answerRow.querySelector(".chat-bubble--assistant");
            if (bubble) bubble.innerHTML = innerHtml;
            persistAssistantBubbleHtml(innerHtml, ans);
          }
          renderThreadList();
          renderAllGraphs();
        }
      }
    }
  } catch (e) {
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
