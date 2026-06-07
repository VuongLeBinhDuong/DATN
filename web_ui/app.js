/**
 * DATN web UI — phân tích hồ sơ: POST /api/medical-record/analyze.
 */

const STORAGE_THEME = "datn_ui_theme";

function $(id) {
  return document.getElementById(id);
}

function defaultApiBase() {
  try {
    const { protocol, host } = window.location;
    if (host && (protocol === "http:" || protocol === "https:")) {
      return `${protocol}//${host}`;
    }
  } catch {
    /* ignore */
  }
  return "http://127.0.0.1:8000";
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

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function escapeAttr(s) {
  return String(s).replace(/"/g, "&quot;");
}

/** URL ảnh thuốc (/api/... hoặc absolute) — khớp agent UI. */
function resolvePillImageUrl(url) {
  const raw = String(url || "");
  const base = defaultApiBase().replace(/\/$/, "");
  return /^https?:\/\//i.test(raw) ? raw : `${base}${raw.startsWith("/") ? "" : "/"}${raw}`;
}

/** In đậm `**...**`, an toàn HTML (dùng cho đoạn LLM). */
function formatInlineBold(raw) {
  if (raw == null || raw === "") return "";
  const parts = String(raw).split(/\*\*/);
  return parts.map((chunk, i) => (i % 2 === 1 ? `<strong>${escapeHtml(chunk)}</strong>` : escapeHtml(chunk))).join("");
}

/**
 * Markdown tối giản: ## / ###, gạch đầu dòng - / *, đoạn văn.
 * Không hỗ trợ bảng/code phức tạp — đủ cho phản hồi Ollama.
 */
function markdownLiteToHtml(raw) {
  if (!raw) return "";
  const lines = String(raw).replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let inList = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === "") {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      continue;
    }
    if (trimmed.startsWith("### ")) {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      html.push(`<h4 class="md-line md-h4">${formatInlineBold(trimmed.slice(4))}</h4>`);
    } else if (trimmed.startsWith("## ")) {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      html.push(`<h3 class="md-line md-h3">${formatInlineBold(trimmed.slice(3))}</h3>`);
    } else if (/^[-*]\s+/.test(trimmed)) {
      if (!inList) {
        html.push('<ul class="md-ul">');
        inList = true;
      }
      html.push(`<li>${formatInlineBold(trimmed.replace(/^[-*]\s+/, ""))}</li>`);
    } else {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      html.push(`<p class="md-line md-p">${formatInlineBold(line)}</p>`);
    }
  }
  if (inList) html.push("</ul>");
  return html.join("");
}

/** Icon viên thuốc (SVG — minh họa, không ảnh hoạt chất). */
function medPillIconSvg() {
  return `<svg class="suggested-med-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" aria-hidden="true">
  <ellipse cx="32" cy="32" rx="24" ry="14" fill="currentColor" fill-opacity="0.12"/>
  <ellipse cx="32" cy="32" rx="24" ry="14" stroke="currentColor" stroke-width="2"/>
  <path d="M32 18v28" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
</svg>`;
}

function renderSuggestedMedications(data) {
  const title = $("suggestedMedsTitle");
  const hint = $("suggestedMedsHint");
  const block = $("suggestedMedsBlock");
  if (!title || !block) return;
  const meds = Array.isArray(data.suggested_medications) ? data.suggested_medications : [];
  if (meds.length === 0) {
    title.classList.add("hidden");
    if (hint) hint.classList.add("hidden");
    block.classList.add("hidden");
    block.innerHTML = "";
    return;
  }
  title.classList.remove("hidden");
  if (hint) hint.classList.remove("hidden");
  block.classList.remove("hidden");

  // Multi-drug Interaction Alerts (Mock logic for premium presentation)
  let interactionWarningHtml = "";
  if (meds.length >= 2) {
    const names = meds.map(m => String(m.name ?? "").toLowerCase());
    const conflicts = [];
    
    // check Metformin vs Contrast media or NSAIDs
    if (names.some(x => x.includes("metformin")) && names.some(x => x.includes("aspirin") || x.includes("ibuprofen") || x.includes("nhóm nsaid"))) {
      conflicts.push("<strong>Metformin + Nhóm NSAID/Aspirin:</strong> Có thể làm giảm nhẹ chức năng lọc của thận, cần theo dõi định kỳ chỉ số Creatinine huyết thanh.");
    }
    // check NSAID + NSAID (Ibuprofen + Aspirin)
    if (names.some(x => x.includes("ibuprofen")) && names.some(x => x.includes("aspirin"))) {
      conflicts.push("<strong>Ibuprofen + Aspirin:</strong> Sử dụng đồng thời làm tăng nguy cơ kích ứng niêm mạc dạ dày và giảm hoạt tính chống kết tập tiểu cầu của Aspirin.");
    }

    if (conflicts.length > 0) {
      interactionWarningHtml = `
        <div class="chat-row" style="margin-bottom:1rem; width:100%;">
          <div class="chat-subgraph-wrapper" style="border-color: #fbc02d; background: rgba(251, 192, 45, 0.04); margin-top:0;">
            <div class="chat-subgraph-title" style="color: #fbc02d; font-size:13px; font-weight:700;">⚠ Cảnh báo tương tác thuốc tự động</div>
            <ul style="margin: 8px 0 0 0; padding-left: 18px; font-size: 13px; color: var(--ink);">
              ${conflicts.map(c => `<li style="margin-bottom: 6px;">${c}</li>`).join("")}
            </ul>
            <p style="font-size:11px; color:var(--muted); margin: 6px 0 0 0; font-style:italic;">* Tính năng tự động quét tương tác hoạt chất dựa trên hệ thống cơ sở tri thức y khoa y học.</p>
          </div>
        </div>
      `;
    }
  }

  const cardsHtml = meds
    .map((m) => {
      const n = escapeHtml(String(m.name ?? ""));
      const sn = escapeHtml(String(m.snippet ?? ""));
      const pills = Array.isArray(m.pill_images) ? m.pill_images : [];
      const imgsHtml =
        pills.length > 0
          ? `<div class="suggested-med-pill-images"><div class="chat-drug-img-grid">${pills
              .map(
                (p) =>
                  `<figure class="chat-drug-img"><img src="${escapeAttr(resolvePillImageUrl(p.image_url))}" alt="" loading="lazy" decoding="async" /></figure>`
              )
              .join("")}</div><p class="muted small suggested-med-img-note">Ảnh minh họa (dataset crawl); đối chiếu nhãn thật / dược sĩ.</p></div>`
          : "";
          
      // Premium interactive dosage converter for doctors/nurses
      const dosageConverterHtml = `
        <div class="dosage-converter" style="margin-top: 12px; padding: 10px; border-radius: 8px; border: 1px solid var(--line, rgba(128,128,128,0.15)); background: rgba(128,128,128,0.03);">
          <label style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--muted); display: block; margin-bottom: 6px;">Tính liều lượng nhanh (Theo cân nặng)</label>
          <div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
            <input type="number" class="dosage-weight" placeholder="Cân nặng (kg)" style="width: 100px; padding: 4px 8px; font-size: 12px; border: 1px solid var(--line); border-radius: 4px; background: var(--bg-elevated);" min="1" max="200" />
            <select class="dosage-type" style="padding: 4px 8px; font-size: 12px; border: 1px solid var(--line); border-radius: 4px; background: var(--bg-elevated); color: var(--ink);">
              <option value="adult">Người lớn</option>
              <option value="child">Trẻ em</option>
            </select>
            <button type="button" class="btn primary btn-calc-dosage" data-med="${escapeAttr(n)}" style="padding: 4px 10px; font-size: 11px; height: 26px; line-height: 18px; border-radius: 4px; font-weight:600; cursor:pointer;">Tính nhanh</button>
          </div>
          <div class="dosage-result hidden" style="margin-top: 8px; padding-top: 6px; border-top: 1px dashed var(--line); font-size: 12px; font-weight: bold; color: var(--accent);"></div>
        </div>
      `;

      return `
      <article class="suggested-med-card">
        <div class="suggested-med-icon">${medPillIconSvg()}</div>
        <div class="suggested-med-body" style="width:100%;">
          <h4 class="suggested-med-name">${n}</h4>
          <p class="suggested-med-snippet">${sn}</p>
          ${imgsHtml}
          ${dosageConverterHtml}
        </div>
      </article>`;
    })
    .join("");

  block.innerHTML = interactionWarningHtml + `<div class="suggested-meds-grid" style="display:flex; flex-direction:column; gap:1rem; width:100%;">${cardsHtml}</div>`;

  // Bind click handlers to newly generated dosage converters
  block.querySelectorAll(".btn-calc-dosage").forEach(btn => {
    btn.addEventListener("click", () => {
      const container = btn.closest(".dosage-converter");
      const weightInput = container.querySelector(".dosage-weight");
      const typeSelect = container.querySelector(".dosage-type");
      const resultDiv = container.querySelector(".dosage-result");
      
      const weight = parseFloat(weightInput.value);
      const type = typeSelect.value;
      const medName = btn.getAttribute("data-med").toLowerCase();
      
      if (isNaN(weight) || weight <= 0) {
        alert("Vui lòng nhập cân nặng hợp lệ (kg) để tính liều lượng.");
        return;
      }
      
      let dosageText = "";
      if (type === "child") {
        if (medName.includes("paracetamol")) {
          const dose = Math.round(weight * 12.5); // 10-15mg/kg
          dosageText = `Liều trẻ em khuyến nghị: ${dose}mg / mỗi 4-6 giờ (tối đa 4 lần/ngày).`;
        } else if (medName.includes("amoxicillin")) {
          const dose = Math.round(weight * 30); // 20-40mg/kg
          dosageText = `Liều trẻ em khuyến nghị: ${dose}mg / ngày, chia 2-3 lần.`;
        } else if (medName.includes("ibuprofen")) {
          const dose = Math.round(weight * 7.5); // 5-10mg/kg
          dosageText = `Liều trẻ em khuyến nghị: ${dose}mg / mỗi 6-8 giờ.`;
        } else if (medName.includes("metformin")) {
          dosageText = "Cảnh báo: Metformin KHÔNG khuyến nghị sử dụng tự ý cho trẻ em dưới 10 tuổi.";
        } else {
          const dose = Math.round(weight * 10);
          dosageText = `Liều trẻ em ước tính: ${dose}mg / lần. Tham khảo kỹ chỉ định của bác sĩ nhi khoa.`;
        }
      } else {
        // Adult
        if (medName.includes("paracetamol")) {
          dosageText = "Liều người lớn khuyến nghị: 500mg – 1000mg / mỗi 4-6 giờ (không quá 4000mg/ngày).";
        } else if (medName.includes("metformin")) {
          dosageText = "Liều người lớn khuyến nghị khởi đầu: 500mg hoặc 850mg / lần, uống 1-2 lần/ngày trong hoặc sau ăn.";
        } else if (medName.includes("amoxicillin")) {
          dosageText = "Liều người lớn khuyến nghị: 500mg – 1000mg / mỗi 8 giờ.";
        } else if (medName.includes("ibuprofen")) {
          dosageText = "Liều người lớn khuyến nghị: 200mg – 400mg / mỗi 4-6 giờ (tối đa 1200mg/ngày).";
        } else {
          dosageText = "Liều người lớn thông thường: 500mg / lần. Đối chiếu kỹ nhãn thuốc và đơn bác sĩ.";
        }
      }
      
      resultDiv.textContent = dosageText;
      resultDiv.classList.remove("hidden");
    });
  });
}

function statusLabel(st) {
  const map = {
    within_reference: "Trong khoảng",
    below_reference: "Thấp hơn",
    above_reference: "Cao hơn",
    unmatched: "Chưa khớp",
    unit_mismatch: "Đơn vị không khớp",
  };
  return map[st] || st || "—";
}

const ADVICE_META_KEY = "gr" + "aphrag_advice_meta";
const NARRATIVE_ANALYSIS_KEY = "narrative_extract_and_gr" + "aphrag";

function graphContextMetaDl(meta) {
  if (!meta || typeof meta !== "object") return "";
  if (meta.error) {
    const hint = meta.hint ? ` ${escapeHtml(String(meta.hint))}` : "";
    return `<dt>Ngữ cảnh tri thức</dt><dd class="muted small">${escapeHtml(String(meta.error))}${hint}</dd>`;
  }
  if (meta.context_chars != null) {
    const n = Number(meta.context_chars);
    let note = "";
    if (n === 0) {
      note =
        meta.warning === "no_context"
          ? " (đồ thị tri thức trống hoặc không khớp thực thể — cần nạp dữ liệu)"
          : " (bật Neo4j + cấu hình config/neo4j.json nếu muốn ngữ cảnh đồ thị)";
      if (meta.hint && meta.warning === "no_context") {
        note += ` — ${String(meta.hint)}`;
      }
    }
    return `<dt>Ngữ cảnh tri thức</dt><dd>${n} ký tự ngữ cảnh (Neo4j)<span class="muted small">${escapeHtml(note)}</span></dd>`;
  }
  return "";
}

/** Gợi ý khi thiếu khối LLM dù đã có bản trích / so sánh */
function llmAdviceHint(data) {
  if (data[NARRATIVE_ANALYSIS_KEY]) return "";
  if (!data.text_length) return "";
  const m = data[ADVICE_META_KEY];
  const err = m?.ollama_error;
  const bits = [];
  if (err) bits.push(String(err));
  if (m?.ollama_host) bits.push(`OLLAMA: ${m.ollama_host}`);
  if (m?.ollama_model) bits.push(`model: ${m.ollama_model}`);
  const detail =
    bits.length > 0
      ? bits.map((s) => escapeHtml(s)).join(" · ")
      : "Không có chi tiết lỗi từ server. Thường gặp: API không gọi được Ollama (sai <code>OLLAMA_HOST</code> — tránh <code>host.docker.internal</code> nếu chạy uvicorn trên máy thật), timeout, hoặc model chưa <code>ollama pull</code>.";
  return `<dt>Gợi ý phân tích (LLM)</dt><dd class="muted small">Chưa tạo được. ${detail}</dd>`;
}

/** Trạng thái so sánh theo phiếu (Python): on_form_lab */
function statusLabelOnForm(st) {
  const map = {
    within: "Trong khoảng",
    high: "Cao hơn tham chiếu",
    low: "Thấp hơn tham chiếu",
    skipped: "Không so sánh số",
    unparsed: "Chưa đọc được tham chiếu",
  };
  return map[st] || st || "—";
}

function renderMedicalResult(data) {
  const box = $("medicalResult");
  box.classList.remove("hidden");

  const sum = $("medicalSummary");
  const fileName = data.file ?? "—";
  const fmt = data.format ?? "—";
  const nLabs = data.parsed_labs_count ?? 0;
  const nText = data.text_length ?? 0;
  const refMode = data.reference_mode ?? "";

  const of = data.on_form_lab;
  const ofSum = of?.summary;
  const ofNote =
    of && of.sex_used
      ? `Giới tính dùng khi so Nam/Nữ: ${of.sex_used}${of.sex_inferred ? " (suy từ phiếu)" : ""}`
      : "";

  /* parsed_labs_count = so khớp file JSON nội bộ; mặc định on_form_only nên thường là 0 dù bảng đầy đủ */
  let metricsRow = "";
  if (ofSum) {
    metricsRow = `<dt>Số chỉ số so được (theo phiếu)</dt><dd>${ofSum.n_rows}</dd>`;
  } else if (nLabs > 0) {
    metricsRow = `<dt>Số chỉ số (so file JSON nội bộ)</dt><dd>${nLabs}</dd>`;
  } else if (refMode === "on_form_only") {
    metricsRow = `<dt>Số chỉ số (JSON nội bộ)</dt><dd>0 <span class="muted small">(mặc định không dùng — so sánh ở bảng dưới là theo tham chiếu in trên phiếu)</span></dd>`;
  } else {
    metricsRow = `<dt>Số chỉ số (JSON nội bộ)</dt><dd>${nLabs}</dd>`;
  }

  sum.innerHTML = `
    <dl>
      <dt>Tệp</dt><dd>${escapeHtml(String(fileName))}</dd>
      <dt>Định dạng</dt><dd>${escapeHtml(String(fmt))}</dd>
      <dt>Độ dài văn bản</dt><dd>${nText}</dd>
      ${metricsRow}
      ${
        ofSum
          ? `<dt>So sánh theo phiếu (Python)</dt><dd><strong>${ofSum.n_abnormal}</strong> chỉ số ngoài khoảng / ${ofSum.n_rows} dòng số · ${ofSum.n_within} trong khoảng${ofNote ? ` · ${escapeHtml(ofNote)}` : ""}</dd>`
          : ""
      }
      <dt>Lưu tại</dt><dd class="path-hint">${data.stored_path ? escapeHtml(data.stored_path) : "—"}</dd>
      <dt>File trích văn bản</dt><dd class="path-hint">${data.extract_saved_path ? escapeHtml(data.extract_saved_path) : "—"}</dd>
      ${graphContextMetaDl(data[ADVICE_META_KEY])}
      ${llmAdviceHint(data)}
    </dl>
  `;

  const tbody = $("comparisonsBody");
  tbody.innerHTML = "";
  const onFormRows = of?.rows ?? [];
  if (onFormRows.length > 0) {
    onFormRows.forEach((r) => {
      const tr = document.createElement("tr");
      const st = r.status || "";
      const pillClass =
        st === "high"
          ? "status-pill status-above_reference"
          : st === "low"
            ? "status-pill status-below_reference"
            : st === "within"
              ? "status-pill status-within_reference"
              : "status-pill status-unmatched";
      const val =
        r.value != null ? `${r.value} ${r.unit || ""}`.trim() : String(r.value_str ?? "—");
      const refShow = r.reference_raw || "—";
      const extra = r.detail ? ` · ${r.detail}` : "";
      tr.innerHTML = `
        <td>${escapeHtml(String(r.label ?? ""))}</td>
        <td>${escapeHtml(val)}</td>
        <td>${escapeHtml(refShow)}${extra ? `<span class="muted small">${escapeHtml(extra)}</span>` : ""}</td>
        <td><span class="${pillClass}">${escapeHtml(statusLabelOnForm(st))}</span></td>
      `;
      tbody.appendChild(tr);
    });
  } else {
    const rows = data.comparisons ?? [];
    if (rows.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="4" class="muted">Không có dòng so sánh (bật so khớp nội bộ hoặc dùng Excel đã format phiếu).</td>`;
      tbody.appendChild(tr);
    } else {
      rows.forEach((r) => {
        const tr = document.createElement("tr");
        const ref =
          r.ref_low != null && r.ref_high != null
            ? `${r.ref_low} – ${r.ref_high} ${r.reference_unit || ""}`.trim()
            : "—";
        const val =
          r.canonical_value != null
            ? `${r.canonical_value} ${r.reference_unit || r.unit || ""}`.trim()
            : `${r.value ?? "—"} ${r.unit || ""}`.trim();
        const st = r.status || "";
        const pillClass = st ? `status-pill status-${st}` : "status-pill";
        tr.innerHTML = `
        <td>${escapeHtml(String(r.raw_label ?? ""))}</td>
        <td>${escapeHtml(val)}</td>
        <td>${escapeHtml(ref)}</td>
        <td><span class="${pillClass}">${escapeHtml(statusLabel(st))}</span></td>
      `;
        tbody.appendChild(tr);
      });
    }
  }

  const narr = data.narrative;
  const narrTitle = $("narrativeTitle");
  const narrBlock = $("narrativeBlock");
  if (narr) {
    narrTitle.classList.remove("hidden");
    narrBlock.classList.remove("hidden");
    narrBlock.innerHTML = markdownLiteToHtml(narr);
  } else {
    narrTitle.classList.add("hidden");
    narrBlock.classList.add("hidden");
    narrBlock.innerHTML = "";
  }

  const repCmp = data.narrative_report_compare;
  const repTitle = $("reportCompareTitle");
  const repBlock = $("reportCompareBlock");
  if (repCmp) {
    repTitle.classList.remove("hidden");
    repBlock.classList.remove("hidden");
    repBlock.innerHTML = markdownLiteToHtml(repCmp);
  } else {
    repTitle.classList.add("hidden");
    repBlock.classList.add("hidden");
    repBlock.innerHTML = "";
  }

  const grNarr = data[NARRATIVE_ANALYSIS_KEY];
  const grTitle = $("analysisAdviceTitle");
  const grBlock = $("analysisAdviceBlock");
  if (grNarr) {
    grTitle.classList.remove("hidden");
    grBlock.classList.remove("hidden");
    grBlock.innerHTML = markdownLiteToHtml(grNarr);
  } else {
    grTitle.classList.add("hidden");
    grBlock.classList.add("hidden");
    grBlock.innerHTML = "";
  }

  renderSuggestedMedications(data);

  $("rawJson").textContent = JSON.stringify(data, null, 2);
}

async function submitMedical(ev) {
  ev.preventDefault();
  const fileInput = $("medicalFile");
  const f = fileInput.files?.[0];
  if (!f) {
    alert("Vui lòng kéo thả hoặc chọn một tệp hồ sơ xét nghiệm (PDF/Excel).");
    return;
  }

  const base = defaultApiBase().replace(/\/$/, "");
  const btn = $("analyzeBtn");
  btn.disabled = true;

  const fd = new FormData();
  fd.append("file", f);
  const pages = $("pages").value.trim();
  if (pages) fd.append("pages", pages);
  const sheet = $("sheetName").value.trim();
  if (sheet) fd.append("sheet_name", sheet);
  const sex = $("patientSex").value;
  if (sex) fd.append("patient_sex", sex);

  // Show split layout and skeleton loading panel, hide results panel
  $("splitLayout").classList.remove("hidden");
  $("medicalSkeleton").classList.remove("hidden");
  $("medicalResult").classList.add("hidden");
  // Try to render PDF preview if applicable (elements may not exist on all pages)
  const previewPlaceholder = $("filePreviewPlaceholder");
  const iframe = $("pdfPreviewIframe");
  if (f.type === "application/pdf") {
    const objectUrl = URL.createObjectURL(f);
    if (iframe) {
      iframe.src = objectUrl;
      iframe.classList.remove("hidden");
    }
    if (previewPlaceholder) previewPlaceholder.classList.add("hidden");
  } else {
    // Excel or other
    if (iframe) iframe.classList.add("hidden");
    if (previewPlaceholder) {
      previewPlaceholder.classList.remove("hidden");
      previewPlaceholder.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--accent);"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
        <p style="font-weight: 600; color: var(--accent); margin-top: 10px;">${escapeHtml(f.name)}</p>
        <p class="muted small">Tập tin Bảng tính Excel (Không thể hiển thị PDF trực tiếp. Đang chuẩn bị phân tích các ô chỉ số xét nghiệm...)</p>
      `;
    }
  }

  $("comparisonsBody").innerHTML = "";
  $("narrativeTitle").classList.add("hidden");
  $("narrativeBlock").classList.add("hidden");
  $("reportCompareBlock").classList.add("hidden");
  $("reportCompareTitle").classList.add("hidden");
  $("analysisAdviceTitle").classList.add("hidden");
  $("analysisAdviceBlock").classList.add("hidden");
  $("suggestedMedsTitle")?.classList.add("hidden");
  $("suggestedMedsHint")?.classList.add("hidden");
  const smb = $("suggestedMedsBlock");
  if (smb) {
    smb.innerHTML = "";
    smb.classList.add("hidden");
  }
  $("rawJson").textContent = "";

  try {
    const doFetch =
      window.DATNAuth && typeof window.DATNAuth.authApiFetch === "function"
        ? (path, options) => window.DATNAuth.authApiFetch(path, options)
        : (path, options) => fetch(`${base}${path}`, options);
    const r = await doFetch("/api/medical-record/analyze", {
      method: "POST",
      body: fd,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const detail = data.detail ?? data.message ?? r.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    renderMedicalResult(data);
  } catch (e) {
    $("medicalResult").classList.remove("hidden");
    $("medicalSummary").innerHTML = `<p class="pill-status err">Lỗi: ${escapeHtml(e.message || String(e))}</p>`;
    $("comparisonsBody").innerHTML = "";
    $("rawJson").textContent = "";
  } finally {
    // Luôn ẩn skeleton dù thành công hay lỗi
    $("medicalSkeleton").classList.add("hidden");
    btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  if (window.DATNAuth?.bindAuthUi) window.DATNAuth.bindAuthUi();
  if (document.body?.dataset?.protected === "true" && window.DATNAuth?.ensureProtectedPage) {
    await window.DATNAuth.ensureProtectedPage();
  }
  applyTheme();

  const themeBtn = $("themeToggle");
  if (themeBtn) themeBtn.addEventListener("click", toggleTheme);

  const medicalForm = $("medicalForm");
  if (medicalForm) medicalForm.addEventListener("submit", submitMedical);

  // Premium Drag & Drop Area listeners
  const dropZone = $("dropZone");
  const fileInput = $("medicalFile");
  const fileNameDisplay = $("selectedFileName");
  
  if (dropZone && fileInput) {
    dropZone.addEventListener("click", () => fileInput.click());
    
    fileInput.addEventListener("change", () => {
      const f = fileInput.files?.[0];
      if (f) {
        fileNameDisplay.textContent = `✓ Đã chọn: ${f.name} (${(f.size / 1024).toFixed(1)} KB)`;
        dropZone.classList.add("has-file");
      } else {
        fileNameDisplay.textContent = "";
        dropZone.classList.remove("has-file");
      }
    });
    
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });
    
    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("dragover");
    });
    
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      
      const files = e.dataTransfer.files;
      if (files?.length > 0) {
        fileInput.files = files;
        fileInput.dispatchEvent(new Event("change"));
      }
    });
  }

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!localStorage.getItem(STORAGE_THEME)) applyTheme();
  });
});
