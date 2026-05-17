const STORAGE_THEME = "datn_ui_theme";
const STORAGE_REMINDERS_V1 = "datn_agent_reminders_v1";
const STORAGE_REMINDERS = "datn_agent_reminders_v2";
const MAX_REMINDERS = 100;
let reminders = [];

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
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

function parseDailyTimes(raw) {
  const parts = String(raw || "").split(/[,;]+/);
  const out = [];
  const seen = new Set();
  for (const p of parts) {
    const m = p.trim().match(/^(\d{1,2}):(\d{2})$/);
    if (!m) continue;
    const h = parseInt(m[1], 10);
    const min = parseInt(m[2], 10);
    if (h < 0 || h > 23 || min < 0 || min > 59) continue;
    const slot = `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
    if (!seen.has(slot)) {
      seen.add(slot);
      out.push(slot);
    }
  }
  return out.sort();
}

function normalizeStoredReminder(x) {
  if (!x || typeof x !== "object") return null;
  if (typeof x.id !== "string" || typeof x.text !== "string" || !x.text.trim()) return null;
  const kind = x.kind || "once";
  if (kind === "daily") {
    const times = (Array.isArray(x.times) ? x.times : []).flatMap((t) => parseDailyTimes(String(t)));
    if (!times.length) return null;
    return { id: x.id, text: x.text.trim(), kind: "daily", times };
  }
  if (kind === "interval") {
    const intervalHours = Math.min(72, Math.max(1, parseInt(String(x.intervalHours), 10) || 6));
    const nextDueIso = String(x.nextDueIso || "");
    if (!nextDueIso) return null;
    return { id: x.id, text: x.text.trim(), kind: "interval", intervalHours, nextDueIso };
  }
  if (typeof x.at === "string") {
    return { id: x.id, text: x.text.trim(), kind: "once", at: x.at };
  }
  return null;
}

function loadReminders() {
  try {
    let raw = localStorage.getItem(STORAGE_REMINDERS);
    if (!raw) raw = localStorage.getItem(STORAGE_REMINDERS_V1);
    if (!raw) return;
    const arr = JSON.parse(raw);
    reminders = Array.isArray(arr) ? arr.map(normalizeStoredReminder).filter(Boolean).slice(-MAX_REMINDERS) : [];
  } catch {
    reminders = [];
  }
}

function saveReminders() {
  try {
    localStorage.setItem(STORAGE_REMINDERS, JSON.stringify(reminders));
  } catch {
    /* ignore */
  }
}

function toYmd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function toHm(d) {
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function startOfDay(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

function make7Days() {
  const arr = [];
  const now = new Date();
  const start = startOfDay(now);
  for (let i = 0; i < 7; i += 1) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    arr.push(d);
  }
  return arr;
}

function weekdayVi(d) {
  const map = ["CN", "Th 2", "Th 3", "Th 4", "Th 5", "Th 6", "Th 7"];
  return map[d.getDay()];
}

function buildEvents(reminders, days) {
  const dayKeys = days.map(toYmd);
  const lastDay = new Date(days[days.length - 1]);
  lastDay.setHours(23, 59, 59, 999);
  const maxMs = lastDay.getTime();
  const events = [];

  for (const r of reminders) {
    if (r.kind === "daily") {
      for (const d of days) {
        const dayKey = toYmd(d);
        for (const hm of r.times) {
          events.push({ dayKey, time: hm, text: r.text, kind: "Hằng ngày" });
        }
      }
      continue;
    }

    if (r.kind === "once") {
      const dt = new Date(r.at);
      if (Number.isNaN(dt.getTime())) continue;
      const dayKey = toYmd(dt);
      if (!dayKeys.includes(dayKey)) continue;
      events.push({ dayKey, time: toHm(dt), text: r.text, kind: "Một lần" });
      continue;
    }

    if (r.kind === "interval") {
      const stepMs = r.intervalHours * 3600000;
      if (!stepMs) continue;
      let t = new Date(r.nextDueIso).getTime();
      if (Number.isNaN(t)) continue;
      let safe = 0;
      while (t <= maxMs && safe < 200) {
        const dt = new Date(t);
        const dayKey = toYmd(dt);
        if (dayKeys.includes(dayKey)) {
          events.push({ dayKey, time: toHm(dt), text: r.text, kind: `Mỗi ${r.intervalHours} giờ` });
        }
        t += stepMs;
        safe += 1;
      }
    }
  }

  return events;
}

function renderSchedule() {
  const wrap = $("scheduleGridWrap");
  if (!wrap) return;
  if (!reminders.length) {
    wrap.innerHTML = `
      <div class="schedule-empty">
        <p>Chưa có lịch nào được lưu.</p>
        <p>Nhấn “+ Thêm lịch mới” để tạo lịch tại trang này.</p>
      </div>
    `;
    return;
  }

  const days = make7Days();
  const events = buildEvents(reminders, days);
  const slots = [...new Set(events.map((e) => e.time))].sort();
  if (!slots.length) {
    wrap.innerHTML = `<p class="chat-muted">Có lịch đã lưu, nhưng chưa có mốc nằm trong 7 ngày tới.</p>`;
    return;
  }

  const byCell = new Map();
  for (const e of events) {
    const key = `${e.dayKey}|${e.time}`;
    if (!byCell.has(key)) byCell.set(key, []);
    byCell.get(key).push(e);
  }

  const head = days
    .map((d) => `<th><div class="sched-day">${weekdayVi(d)}</div><div class="sched-date">${d.toLocaleDateString("vi-VN")}</div></th>`)
    .join("");

  const rows = slots
    .map((time) => {
      const tds = days
        .map((d) => {
          const key = `${toYmd(d)}|${time}`;
          const items = byCell.get(key) || [];
          if (!items.length) return `<td class="sched-cell"></td>`;
          const cards = items
            .map(
              (x) => `<div class="sched-pill">
                <div class="sched-pill-title">${escapeHtml(x.text)}</div>
                <div class="sched-pill-kind">${escapeHtml(x.kind)}</div>
              </div>`
            )
            .join("");
          return `<td class="sched-cell sched-cell--filled">${cards}</td>`;
        })
        .join("");
      return `<tr><th class="sched-time">${time}</th>${tds}</tr>`;
    })
    .join("");

  wrap.innerHTML = `
    <div class="schedule-table-scroll">
      <table class="schedule-table">
        <thead>
          <tr>
            <th>Giờ</th>
            ${head}
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function formatReminderLine(r) {
  if (r.kind === "daily") return `Mỗi ngày: ${r.times.join(", ")}`;
  if (r.kind === "interval") {
    const d = new Date(r.nextDueIso);
    return `Mỗi ${r.intervalHours} giờ · lần tới: ${Number.isNaN(d.getTime()) ? r.nextDueIso : d.toLocaleString("vi-VN")}`;
  }
  const x = new Date(r.at);
  return Number.isNaN(x.getTime()) ? r.at : x.toLocaleString("vi-VN");
}

function renderManagerList() {
  const box = $("scheduleManagerList");
  if (!box) return;
  if (!reminders.length) {
    box.innerHTML = `<p class="chat-muted">Chưa có lịch nào để quản lý.</p>`;
    return;
  }
  const sorted = [...reminders].sort((a, b) => String(formatReminderLine(a)).localeCompare(String(formatReminderLine(b))));
  box.innerHTML = sorted
    .map((r) => {
      const kind = r.kind === "daily" ? "Hằng ngày" : r.kind === "interval" ? "Cách N giờ" : "Một lần";
      return `<div class="schedule-item-row">
        <div class="schedule-item-main">
          <div class="schedule-item-title">${escapeHtml(r.text)}</div>
          <div class="schedule-item-meta"><span class="schedule-item-kind">${escapeHtml(kind)}</span> · ${escapeHtml(formatReminderLine(r))}</div>
        </div>
        <div class="schedule-item-actions">
          <button type="button" class="btn ghost" data-edit-id="${escapeHtml(r.id)}">Sửa</button>
          <button type="button" class="btn secondary" data-delete-id="${escapeHtml(r.id)}">Xóa</button>
        </div>
      </div>`;
    })
    .join("");

  box.querySelectorAll("[data-edit-id]").forEach((btn) => {
    btn.addEventListener("click", () => openEditor(btn.getAttribute("data-edit-id")));
  });
  box.querySelectorAll("[data-delete-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-delete-id");
      if (!id) return;
      reminders = reminders.filter((x) => x.id !== id);
      saveReminders();
      rerenderAll();
    });
  });
}

function rerenderAll() {
  renderSchedule();
  renderManagerList();
}

function currentKind() {
  return document.querySelector('input[name="scheduleKind"]:checked')?.value || "once";
}

function syncEditorSections() {
  const kind = currentKind();
  $("scheduleFieldsOnce")?.classList.toggle("hidden", kind !== "once");
  $("scheduleFieldsDaily")?.classList.toggle("hidden", kind !== "daily");
  $("scheduleFieldsInterval")?.classList.toggle("hidden", kind !== "interval");
  const when = $("scheduleWhen");
  if (when) when.required = kind === "once";
}

function newId(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function toLocalInputValue(date) {
  const d = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return d.toISOString().slice(0, 16);
}

function openEditor(editId = "") {
  const dlg = $("scheduleEditorDialog");
  const edit = editId ? reminders.find((x) => x.id === editId) : null;
  $("scheduleEditId").value = edit ? edit.id : "";
  $("scheduleText").value = edit?.text || "";

  const nowLocal = toLocalInputValue(new Date());
  $("scheduleWhen").value = nowLocal;
  $("scheduleDailyTimes").value = "08:00, 20:00";
  $("scheduleIntervalHours").value = "6";
  $("scheduleIntervalStart").value = nowLocal;

  const kind = edit?.kind || "once";
  const radio = document.querySelector(`input[name="scheduleKind"][value="${kind}"]`);
  if (radio) radio.checked = true;
  if (edit?.kind === "once") {
    const d = new Date(edit.at);
    if (!Number.isNaN(d.getTime())) $("scheduleWhen").value = toLocalInputValue(d);
  } else if (edit?.kind === "daily") {
    $("scheduleDailyTimes").value = edit.times.join(", ");
  } else if (edit?.kind === "interval") {
    $("scheduleIntervalHours").value = String(edit.intervalHours);
    const d = new Date(edit.nextDueIso);
    if (!Number.isNaN(d.getTime())) $("scheduleIntervalStart").value = toLocalInputValue(d);
  }
  syncEditorSections();
  if (typeof dlg?.showModal === "function") dlg.showModal();
}

function closeEditor() {
  const dlg = $("scheduleEditorDialog");
  if (typeof dlg?.close === "function") dlg.close();
}

function submitEditor(e) {
  e.preventDefault();
  const id = $("scheduleEditId").value || newId("r");
  const text = String($("scheduleText").value || "").trim();
  const kind = currentKind();
  if (!text) return;
  let item = null;
  if (kind === "once") {
    const v = $("scheduleWhen").value;
    if (!v) return;
    item = { id, text, kind: "once", at: new Date(v).toISOString(), notified: false };
  } else if (kind === "daily") {
    const times = parseDailyTimes($("scheduleDailyTimes").value || "");
    if (!times.length) {
      alert("Nhập giờ hợp lệ, ví dụ: 08:00, 20:00");
      return;
    }
    item = { id, text, kind: "daily", times, lastFired: {} };
  } else {
    const intervalHours = Math.min(72, Math.max(1, parseInt(String($("scheduleIntervalHours").value), 10) || 6));
    const v = $("scheduleIntervalStart").value;
    const startIso = v ? new Date(v).toISOString() : new Date().toISOString();
    item = { id, text, kind: "interval", intervalHours, nextDueIso: startIso };
  }
  const idx = reminders.findIndex((x) => x.id === id);
  if (idx >= 0) reminders[idx] = item;
  else reminders.push(item);
  if (reminders.length > MAX_REMINDERS) reminders = reminders.slice(-MAX_REMINDERS);
  saveReminders();
  closeEditor();
  rerenderAll();
}

document.addEventListener("DOMContentLoaded", () => {
  if (window.DATNAuth?.bindAuthUi) window.DATNAuth.bindAuthUi();
  applyTheme();
  $("themeToggle")?.addEventListener("click", toggleTheme);
  loadReminders();
  $("refreshScheduleBtn")?.addEventListener("click", rerenderAll);
  $("openScheduleEditorBtn")?.addEventListener("click", () => openEditor(""));
  $("closeScheduleEditorBtn")?.addEventListener("click", closeEditor);
  $("scheduleEditorForm")?.addEventListener("submit", submitEditor);
  document.querySelectorAll('input[name="scheduleKind"]').forEach((x) => x.addEventListener("change", syncEditorSections));
  rerenderAll();
});
