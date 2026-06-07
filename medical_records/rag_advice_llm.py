"""GraphRAG (Neo4j) + LLM: một khối trả lời — chỉ số lệch, nguyên nhân, xử lý, nhóm thuốc tham khảo; trích dẫn theo khối trong ngữ cảnh đồ thị.

**Chất lượng** phụ thuộc đồ thị đã import (``scripts/graphrag_parquet_to_neo4j.py``) và ``config/neo4j.json``
(enabled + query_backend neo4j). Chuỗi truy vấn ghép từ phiếu: :func:`build_graphrag_query_from_extract`.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)

from llm_pipeline.neo4j_graphrag import load_neo4j_config, neo4j_enabled, retrieve_graph_context

_MAX_EXTRACT = int(os.getenv("MEDICAL_RECORD_RAG_ADVICE_MAX_EXTRACT", "12000"))
_MAX_GRAPHRAG_QUERY = int(
    os.getenv("MEDICAL_RECORD_GRAPHRAG_QUERY_CHARS")
    or os.getenv("MEDICAL_RECORD_RAG_QUERY_CHARS")
    or "2500"
)

# Tránh model nhại lại toàn bộ bullet hướng dẫn trong câu trả lời.
_SYSTEM_NO_INSTRUCTION_ECHO_VI = (
    "Bạn tuân thủ tin nhắn user nhưng TUYỆT ĐỐI không sao chép các bullet quy tắc nội bộ vào câu trả lời. "
    "Trả lời **một khối** duy nhất: theo từng chỉ số lệch — nguyên nhân, xử lý, và có thể đề xuất thuốc phù hợp (tên, liều tham khảo, cách dùng); "
    "tham chiếu đúng phiếu; không sai sinh lý (insulin không do gan)."
)
_SYSTEM_NO_INSTRUCTION_ECHO_EN = (
    "Follow the user message but NEVER paste the internal rule bullets into your reply. "
    "Single unified answer: per abnormal lab — causes, actions, and appropriate medication suggestions "
    "(names, doses, schedules) when justified; quote refs as on form; no false physiology (insulin not from liver)."
)

_LAB_LINE_PATTERN = re.compile(
    r"(?i)glucose|ure|creatinin|creatinine|ast|alt|ggt|sgot|sgpt|cholesterol|triglyceride|"
    r"hdl|ldl|uric|acid uric|protein|albumin|bilirubin|natri|kali|clo|tsh|ft3|ft4|hemoglobin|"
    r"định lượng|men gan|thận|lipid|đường huyết|sắt|ferritin|crp|canxi|amylase|ck-mb|"
    r"negative|positive|mmol|µmol|umol|u/l|iu/l|g/l|pg/ml"
)

_LABEL_BEFORE_COLON = re.compile(r"^\s*([^:|]{2,55})\s*:\s*")
_SKIP_LABEL_PREFIX = re.compile(
    r"(?i)^(họ tên|bệnh viện|phiếu|mã code|ngày xét|chẩn đoán|bác sĩ|loại mẫu|"
    r"xét nghiệm\s*\||---\s*sheet|tổng phân tích)"
)


def _extract_lab_name_hints(extract: str, *, max_labels: int = 28) -> str:
    """Danh sách tên xét nghiệm/chỉ số suy ra từ các dòng 'Tên: giá trị...' trong bản trích."""
    labels: list[str] = []
    seen: set[str] = set()
    for line in (extract or "").splitlines():
        t = line.strip()
        if len(t) < 5:
            continue
        m = _LABEL_BEFORE_COLON.match(t)
        if not m:
            continue
        lab = m.group(1).strip()
        if _SKIP_LABEL_PREFIX.match(lab):
            continue
        low = lab.casefold()
        if low in seen:
            continue
        seen.add(low)
        labels.append(lab)
        if len(labels) >= max_labels:
            break
    return "; ".join(labels)


def _compact_lab_hints_for_retrieval(extract: str) -> str:
    """Chuỗi ngắn từ tên chỉ số (đặt đầu câu truy vấn Neo4j fulltext — chỉ ~512 ký tự đầu được dùng)."""
    s = _extract_lab_name_hints(extract or "")
    if not s:
        return ""
    parts = [x.strip() for x in s.split(";") if x.strip()]
    return " ".join(parts)


def build_graphrag_query_from_extract(extract: str, max_chars: int) -> str:
    """
    Ghép câu hỏi truy vấn đồ thị từ bản trích: tiền tố tên chỉ số + các dòng có từ khóa lab; thêm đoạn giữa/cuối.

    Có thể thêm cố định: env ``MEDICAL_RECORD_GRAPHRAG_QUERY_PREFIX``, ``MEDICAL_RECORD_GRAPHRAG_QUERY_SUFFIX``
    (hoặc tương thích ``MEDICAL_RECORD_RAG_QUERY_PREFIX`` / ``_SUFFIX``).
    """
    raw = extract or ""
    if not raw.strip():
        return ""
    max_chars = max(200, max_chars)

    prefix = (
        os.getenv("MEDICAL_RECORD_GRAPHRAG_QUERY_PREFIX")
        or os.getenv("MEDICAL_RECORD_RAG_QUERY_PREFIX")
        or ""
    ).strip()
    suffix = (
        os.getenv("MEDICAL_RECORD_GRAPHRAG_QUERY_SUFFIX")
        or os.getenv("MEDICAL_RECORD_RAG_QUERY_SUFFIX")
        or ""
    ).strip()
    name_hints = _extract_lab_name_hints(raw)
    topic_line = ""
    if name_hints:
        topic_line = (
            "Chủ đề xét nghiệm trên phiếu (tên chỉ số suy từ bản trích): "
            + name_hints
            + ".\n\n"
        )
    lines = raw.splitlines()
    picked: list[str] = []
    seen: set[str] = set()
    for line in lines:
        t = line.strip()
        if not t or len(t) > 600:
            continue
        if not _LAB_LINE_PATTERN.search(t):
            continue
        key = t[:160]
        if key in seen:
            continue
        seen.add(key)
        picked.append(t)
    focus = "\n".join(picked)
    third = max(350, max_chars // 3)
    nlen = len(raw)
    mid_start = max(0, nlen // 4)
    middle = raw[mid_start : mid_start + third]
    tail = raw[-third:] if nlen > third else ""
    if len(focus) >= min(max_chars // 2, 400):
        body = focus
    else:
        glue = "\n...\n"
        body = (focus + glue + middle + glue + tail).strip()
    if not body.strip():
        body = raw
    core = f"{topic_line}{body}".strip()
    if prefix:
        core = f"{prefix}\n\n{core}"
    if suffix:
        core = f"{core}\n\n{suffix}"
    out = core[:max_chars]
    return out if out.strip() else raw[:max_chars]


def fetch_graphrag_context(
    query_from_extract: str,
    *,
    top_k: int = 6,
    graphrag_query_chars: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Truy vấn GraphRAG trên Neo4j (:func:`retrieve_graph_context`) với câu hỏi từ :func:`build_graphrag_query_from_extract`.

    Cần ``config/neo4j.json`` với ``enabled: true`` và ``query_backend: neo4j``.

    Trả về (chuỗi ngữ cảnh đồ thị, meta). Nếu lỗi / không cấu hình: meta['error'] và chuỗi rỗng.
    Neo4j dùng file cố định ``config/neo4j.json``.
    """
    n_src = graphrag_query_chars
    n = n_src if n_src is not None else int(_MAX_GRAPHRAG_QUERY)
    hints = _extract_lab_name_hints(query_from_extract or "")
    compact = _compact_lab_hints_for_retrieval(query_from_extract or "")
    query = build_graphrag_query_from_extract(query_from_extract or "", max(200, n))
    # Neo4j retrieve_graph_context → _fulltext_safe_query chỉ dùng ~512 ký tự ĐẦU của chuỗi.
    # build_graphrag_query_from_extract thường bắt đầu bằng câu tiếng Việt dài → fulltext không trúng entity (corpus EN).
    # Đưa tên xét nghiệm (Glucose, Ure, …) lên trước để Lucene khớp chỉ mục.
    if compact:
        query = f"{compact}\n\n{query}"
    meta: dict[str, Any] = {
        "backend": "neo4j_graphrag",
        "top_k_nodes_requested": top_k,
        "query_len": len(query),
        "query_strategy": "lab_focused",
        "lab_name_hints": hints,
        "retrieval_query_prefix": (compact[:240] + "…") if len(compact) > 240 else compact,
        "graphrag_query_preview": (query[:700] + "…") if len(query) > 700 else query,
    }
    if not query.strip():
        meta["error"] = "empty_query"
        return "", meta

    neo_cfg = load_neo4j_config()
    if not neo4j_enabled(neo_cfg) or neo_cfg is None:
        meta["error"] = "graphrag_neo4j_not_enabled"
        meta["hint"] = (
            "Bật Neo4j GraphRAG trong config/neo4j.json (enabled: true, query_backend: neo4j) "
            "và import đồ thị (vd. run_pipeline.ps1 -SyncGraphragToNeo4j)."
        )
        return "", meta

    cfg = dict(neo_cfg)
    cfg["top_k_nodes"] = max(1, min(int(top_k), int(cfg.get("top_k_nodes") or 12)))

    try:
        ctx = retrieve_graph_context(query, cfg)
    except Exception as exc:  # noqa: BLE001
        meta["error"] = str(exc)
        return "", meta

    if not (ctx or "").strip() and compact:
        try:
            ctx_fb = retrieve_graph_context(compact[:500], cfg)
            if (ctx_fb or "").strip():
                ctx = ctx_fb
                meta["retrieval_fallback"] = "lab_hints_only"
        except Exception as exc_fb:  # noqa: BLE001
            meta["retrieval_fallback_error"] = str(exc_fb)

    max_ctx = int(os.getenv("MEDICAL_RECORD_GRAPHRAG_MAX_CONTEXT_CHARS", "12000"))
    if len(ctx) > max_ctx:
        ctx = ctx[:max_ctx] + "\n\n[… đã cắt bớt ngữ cảnh GraphRAG theo MEDICAL_RECORD_GRAPHRAG_MAX_CONTEXT_CHARS]"

    meta["context_chars"] = len(ctx)
    if not ctx.strip():
        meta["warning"] = "no_context"
        meta["hint"] = (
            "Fulltext Neo4j không trả entity/community. Kiểm tra import GraphRAG; "
            "hoặc corpus không chứa chủ đề trùng từ khóa trên phiếu."
        )
        return "", meta
    return ctx, meta


def llm_extract_reasoning_plus_graphrag_advice(
    extracted_text: str,
    graphrag_context: str,
    *,
    language: str = "vi",
    max_extract_chars: int | None = None,
    lab_compare_block: str | None = None,
    meta_out: dict[str, Any] | None = None,
) -> str | None:
    """
    Một lần gọi LLM — **một khối** trả lời (không tách PHẦN A/B):
    ưu tiên chỉ phân tích chỉ số **bất thường** khi có ``lab_compare_block``;
    với mỗi chỉ số đó: nguyên nhân có thể, hướng xử lý, nhóm thuốc tham khảo (giáo dục);
    trích dẫn khối GraphRAG (entity / community) khi sát chủ đề.
    """
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    timeout = int(os.getenv("MEDICAL_RECORD_OLLAMA_TIMEOUT") or os.getenv("OLLAMA_TIMEOUT") or "180")
    if meta_out is not None:
        meta_out["ollama_host"] = host
        meta_out["ollama_model"] = model
    cap = max_extract_chars if max_extract_chars is not None else _MAX_EXTRACT
    body = (extracted_text or "")[:cap]
    if len(extracted_text or "") > cap:
        body += "\n\n[... đã cắt bớt cho ngữ cảnh model; bản đầy đủ có upstream.]"
    lab_block = (lab_compare_block or "").strip()
    lab_section_vi = (
        f"""### KẾT QUẢ SO SÁNH (Python — ưu tiên đọc trước)
{lab_block}

**Bắt buộc:** Chỉ viết phân tích chi tiết (nguyên nhân, xử lý, thuốc tham khảo) cho **đúng các chỉ số** Python liệt kê là **cao/thấp** (ngoài khoảng). **Cấm** viết mục `###` riêng cho chỉ số chỉ xuất hiện trong danh sách «ĐÃ trong khoảng» hoặc «trong khoảng tham chiếu» ở khối trên — kể cả khi *Bản trích phiếu* vẫn nhắc tên đó. **Cấm** gán rối loạn đường huyết / cường giáp / v.v. cho glucose, insulin, TSH… nếu Python đã xác định **trong khoảng**. **Không** mâu thuẫn trạng thái. **Không** tạo mục cho xét nghiệm không có trên phiếu (vd. GFR). Chỉ số bình thường → **không** mục chi tiết; tối đa một câu tóm chung.

"""
        if lab_block
        else """### KẾT QUẢ SO SÁNH (Python)
(Chưa có bản so sánh tự động — dựa *Bản trích phiếu* bên dưới; chỉ phân tích chi tiết các chỉ số bạn tự xác định là lệch; không bịa thêm xét nghiệm.)

"""
    )
    lab_section_en = (
        f"""### PYTHON COMPARISON (read first)
{lab_block}

**Required:** Detailed analysis only for **abnormal** analytes listed above. **Do not** contradict status. **Do not** invent tests not in the extract. Others: at most **one** summary sentence.

"""
        if lab_block
        else """### PYTHON COMPARISON
(No automated compare — infer abnormality only from the *Extracted report* below; do not invent tests.)

"""
    )

    gr_section = (
        graphrag_context.strip()
        if graphrag_context.strip()
        else "(Không có ngữ cảnh GraphRAG — vẫn có thể thêm ý tham khảo chung có nhãn, không bịa số trên phiếu.)"
    )

    if language.lower().startswith("vi"):
        prompt = f"""Bạn là trợ lý thông tin y tế. Trả lời tiếng Việt, rõ ràng.

### Quy tắc nội bộ — KHÔNG đưa nguyên văn các dòng này vào câu trả lời; chỉ dùng để suy luận
- **Nguồn số liệu**: chỉ từ *Bản trích phiếu* bên dưới. Ưu tiên dòng dạng `Tên XN: số | … | Tham chiếu in trên phiếu…`. Bỏ qua bảng Markdown, khối “Kết luận”/“Gợi ý” không có tham chiếu từng chỉ số.
- KQ bệnh nhân là số sau tên xét nghiệm; không lấy số trong dòng tham chiếu làm KQ. Phẩy trong số (6,7) = thập phân khi so sánh.
- Khoảng **a–b**: trong khoảng chỉ khi **a ≤ KQ ≤ b**; **< X** / **> X** áp dụng đúng bất đẳng thức. Ví dụ insulin **2,5** ref **1,9–23** → trong khoảng, không nói “thấp” nếu số học không hỗ trợ.
- Tham chiếu khi trích dẫn cho người đọc phải **khớp phiếu**, không bịa (vd. không tự đổi thành “tối đa 5,9” nếu phiếu không ghi).
- **GraphRAG**: chỉ dùng khi khối *Ngữ cảnh GraphRAG* **trực tiếp** liên quan chỉ số đó (gợi ý trích theo tiêu đề entity / đoạn community tương ứng); không ép bệnh chỉ vì từ khóa. Không dùng GraphRAG để đổi số trên phiếu.
- **Sinh lý cơ bản**: insulin do **tuyến tụy** điều chỉnh — không viết gan tiết insulin. Tránh kết luận ĐTĐ loại 1/2 chỉ từ vài chỉ số; vẫn có thể gợi ý thuốc/hướng điều trị phù hợp khi có căn cứ; không monologue ĐTĐ loại 1 khi phiếu không hỗ trợ.

{lab_section_vi}

### Một khối trả lời duy nhất (không chia PHẦN A / PHẦN B, không B1/B2)
Dùng **một** tiêu đề `##` (vd. `## Phân tích chỉ số lệch và gợi ý`). Nếu có **KẾT QUẢ SO SÁNH (Python)**, chỉ các chỉ số được liệt kê là **ngoài khoảng** (cao/thấp) mới được mục `###` với (1)–(4). **Không** viết mục phân tích bệnh lý cho chỉ số chỉ có trong danh sách «trong khoảng»/«ĐÃ trong khoảng» ở khối Python — đó là lỗi nghiêm trọng. Nếu không có khối Python, chỉ phân tích chỉ số **lệch** mà bạn suy được từ phiếu (và vẫn **không** mâu thuẫn nếu sau đó có so sánh số học).
Bên trong, với **mỗi** chỉ số **được phép phân tích** (chỉ ngoài khoảng theo Python, hoặc lệch rõ từ phiếu khi không có Python), viết **gọn** (`### Tên chỉ số` hoặc gạch đầu dòng), mỗi chỉ số gồm:
1) **Tóm tắt**: tên — KQ so với tham chiếu **đúng như in** (một dòng).
2) **Nguyên nhân / yếu tố có thể** (học thuật, không chẩn đoán xác định cá nhân).
3) **Cách xử lý**: lối sống, theo dõi, các bước không dùng thuốc nếu phù hợp.
4) **Thuốc**: có thể đề xuất thuốc phù hợp (hoạt chất hoặc biệt dược thông dụng, liều và lịch tham khảo) căn cứ phiếu + GraphRAG + kiến thức điều trị; nêu tương tác/chống chỉ định quan trọng khi có cơ sở.

Trích ý từ *Ngữ cảnh GraphRAG* xen trong (1)–(4) khi phù hợp (ghi rõ đang tham chiếu phần entity/community nào). Phần không dựa GraphRAG thì mở đầu câu bằng *Tham khảo chung — không thay thuốc đã kê.*

Nếu **không** có chỉ số lệch: vài câu theo dõi định kỳ.

**Cấm** dán lại toàn bộ phiếu (`--- Sheet:`, header BV, bảng `| … |`). Người đọc đã có file.

---

### BẢN TRÍCH PHIẾU
{body}

---

### NGỮ CẢNH GRAPHRAG (Neo4j — tra cứu tri thức, không thay số trên phiếu)
{gr_section}
"""
    else:
        prompt = f"""You are a medical information assistant. Answer in clear English.

### Internal rules — do NOT paste these bullets into your reply; use only for reasoning
- **Data** comes only from *Extracted report* below. Prefer structured lines (`Test: value | … | reference on form…`). Ignore Markdown tables or narrative “conclusions” without per-test references.
- Result vs reference: same rules as before (intervals, <, >; comma decimals). Do not call a value “low” if math says within range (e.g. insulin 2.5 vs 1.9–23).
- When quoting bounds for the reader, use **exactly** what is printed — do not invent “max 5.9” etc.
- **GraphRAG context**: cite only when a block (entity title / community summary) is **directly** relevant to that analyte; do not force a disease narrative. Do not use GraphRAG to change report numbers.
- **Physiology**: insulin is from **pancreatic** regulation — not the liver. Avoid labeling T1/T2 from a single slip alone; you may still suggest appropriate meds when justified; no long type-1 monologue if the report does not support it.

{lab_section_en}

### Single unified answer (no Part A / Part B, no B1/B2)
Use **one** main `##` heading (e.g. `## Abnormal results: causes and guidance`). If **PYTHON COMPARISON** lists abnormal analytes, **only** those get detailed subsections (1)–(4) below — **do not** iterate every normal line. If no Python block, only analyse analytes you determine abnormal from the extract.
For **each** analyte that needs analysis, write a compact subsection (`###` or bullets) with:
1) **One-line summary**: name — result vs **printed** reference.
2) **Possible causes / factors** (educational, not a personal diagnosis).
3) **What to do**: lifestyle, monitoring, non-drug steps when appropriate.
4) **Medications**: you may suggest specific drugs with doses and schedules when appropriate to the report and GraphRAG context; note key interactions/contraindications when grounded.

Weave GraphRAG context into (2)–(4) where relevant (name the entity/community slice). For sentences not grounded there, start with *General reference.*

If **no** abnormal results: brief routine follow-up.

**Do not** paste the raw report (`--- Sheet:`, headers, full tables).

---

### EXTRACTED REPORT
{body}

---

### GRAPHRAG CONTEXT (Neo4j — knowledge lookup; do not alter report numbers)
{gr_section}
"""

    try:
        try:
            from core.settings import get_settings
            num_ctx = get_settings().ollama.num_ctx
        except Exception:
            try:
                num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
            except ValueError:
                num_ctx = 16384

        url = host + "/api/chat"
        sys_msg = (
            _SYSTEM_NO_INSTRUCTION_ECHO_VI
            if language.lower().startswith("vi")
            else _SYSTEM_NO_INSTRUCTION_ECHO_EN
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.15,
                "num_ctx": num_ctx,
            },
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        if meta_out is not None:
            meta_out["ollama_http_status"] = resp.status_code
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("message", {}) or {}).get("content", "").strip()
        if not content:
            if meta_out is not None:
                meta_out["ollama_error"] = "model_trả_về_nội_dung_rỗng"
            logger.warning("medical RAG advice: Ollama returned empty content")
            return None
        return content
    except requests.HTTPError as exc:
        err_txt = str(exc)
        if exc.response is not None:
            try:
                err_txt = exc.response.text[:500]
            except Exception:
                pass
            if meta_out is not None:
                meta_out["ollama_error"] = f"HTTP {exc.response.status_code}: {err_txt}"
        elif meta_out is not None:
            meta_out["ollama_error"] = err_txt
        logger.warning("medical RAG advice: Ollama HTTP error: %s", err_txt)
        return None
    except requests.RequestException as exc:
        if meta_out is not None:
            meta_out["ollama_error"] = str(exc)[:800]
        logger.warning("medical RAG advice: Ollama request failed: %s", exc)
        return None
