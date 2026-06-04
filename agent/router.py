"""[LEGACY pipeline] Điều phối nhánh social | graphrag — chỉ dùng khi ``orchestrator`` / ``langgraph_app`` (không ReAct).

Định tuyến kiểu NeMo *router_agent*: danh sách nhánh có mô tả → LLM chọn **một tên nhánh** → pipeline gọi tool tương ứng.

- ``graph`` / không ``auto``: luôn nhánh ``graphrag`` (luôn gọi GraphRAG).
- ``auto``: mặc định có **heuristic** (regex) cho chào hỏi / xin phép hỏi → ``social``; còn lại LLM chọn ``social`` | ``graphrag``.

**Có bắt buộc phải có pattern/hint không?** Không. Với *NeMo ReAct* (``workflow._type: react_agent`` trong ví dụ
``NeMo-Agent-Toolkit/examples/agents/react/configs/config.yml``), prompt nói rõ: nếu **không cần tool** thì model có thể
đi thẳng tới **Final Answer** (chào hỏi = completion thuần, không Action). Không có file pattern Python — chỉ mô tả tool
trong YAML + system prompt.

Ở DATN, heuristic chỉ là **tối ưu tùy chọn**: giảm 1 lần gọi router LLM và giảm lỗi model nhỏ chọn nhầm ``graphrag``.
Tắt bằng ``AGENT_ROUTER_HEURISTICS=0`` (hoặc ``false``) để giống tinh thần ReAct: mọi quyết định nhánh do LLM router.

Cách cấu hình nhánh tương tự NeMo ``examples/agents/router``: ``name`` + ``description`` → prompt; thực thi đúng nhánh
(không gọi ``tool_graphrag_query`` nếu ``social``).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import requests

from core.settings import get_settings

ALLOWED_ROUTES = frozenset({"social", "graphrag"})
_LEGACY_DIRECT = "direct"

DEFAULT_ROUTER_RETRIES = 3


def _router_heuristics_enabled() -> bool:
    v = (os.getenv("AGENT_ROUTER_HEURISTICS") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


@dataclass(frozen=True)
class RouterBranch:
    """Một nhánh điều phối — tương tự branch/tool trong NeMo ``router_agent`` (tên + mô tả cho LLM)."""

    name: str
    description: str


# Đổi mô tả tại đây giống chỉnh ``functions:`` / mô tả tool trong YAML NeMo.
ROUTER_BRANCHES: tuple[RouterBranch, ...] = (
    RouterBranch(
        "social",
        "Trả lời trực tiếp, không tra kho: chào hỏi, cảm ơn, tạm biệt; xin phép hỏi chưa nêu triệu chứng/thuốc; "
        "lịch sự ngắn (kể cả «hello», «hi», «thanks»); emoji. Không cần tài liệu y khoa đã chỉ mục.",
    ),
    RouterBranch(
        "graphrag",
        "Gọi công cụ tra cứu kho tri thức đồ thị (GraphRAG): câu hỏi hoặc mô tả về sức khỏe, thuốc, triệu chứng, "
        "xét nghiệm, phòng bệnh, «có nguy hiểm không», «nên làm gì», hoặc bất kỳ nội dung cần căn cứ tài liệu.",
    ),
)


@dataclass(frozen=True)
class RetrievalPlan:
    use_graphrag: bool
    reason: str
    router_route: str | None = None
    next_pipeline: str | None = None


DEFAULT_ROUTER_MODEL = "qwen2.5:1.5b-instruct"


def _next_pipeline(route: str) -> str:
    return "social_llm" if route == "social" else "rag_llm"


def _branch_catalog_text() -> str:
    return "\n".join(f"- {b.name}: {b.description}" for b in ROUTER_BRANCHES)


def _branch_names_csv() -> str:
    return ",".join(b.name for b in ROUTER_BRANCHES)


def is_obvious_pure_social(question: str) -> bool:
    """Chào hỏi cực ngắn — bỏ qua LLM (NeMo vẫn có thể route bằng LLM; ta tối ưu latency + ổn định)."""
    q = (question or "").strip()
    if not q or len(q) > 160:
        return False
    n = q.strip()
    patterns = (
        r"^(hello|hi|hey|hiya|yo)(\s+(there|all|everyone|mate|friend|guys))?\s*[!?.。…]*$",
        r"^(good\s+(morning|afternoon|evening|night))(\s+everyone)?\s*[!?.。…]*$",
        r"^(xin\s+chào|xin\s+chao|chao(\s+ban)?|chào(\s+(bạn|ban|anh|chị|chi|em|cô|chú))?|alo|a\s+lô)\s*[!?.。…]*$",
        r"^(tạm\s+biệt|tam\s+biet|bye|goodbye|see\s+ya|see\s+you)(\s+(soon|everyone))?\s*[!?.。…]*$",
        r"^(cảm\s+ơn|cam\s+on|thank\s+you|thanks)(\s+(you|bạn|ban|nhé|nhe))?\s*[!?.。…]*$",
        r"^(ok|okay|ừ|ừm|uhm|dạ|vâng|yes|no)\s*[!?.。…]*$",
    )
    return any(re.match(p, n, re.IGNORECASE) for p in patterns)


_MEDICAL_HINT = re.compile(
    r"(triệu\s*chứng|thuốc|bệnh|đau\s|sốt|viêm|uống\s+thuốc|kháng\s*sinh|"
    r"xét\s*nghiệm|huyết\s*áp|tiểu\s*đường|tim\s+mạch|gan|phổi|buồn\s*nôn|ho\s|"
    r"paracetamol|ibuprofen|điều\s*trị|chẩn\s*đoán)",
    re.IGNORECASE,
)


def is_meta_conversational_opener(question: str) -> bool:
    """Xin phép hỏi, chưa có nội dung y tế — chọn nhánh social, không gọi tool GraphRAG."""
    q = (question or "").strip()
    if not q or len(q) > 220:
        return False
    low = q.lower()
    if _MEDICAL_HINT.search(low):
        return False
    patterns = (
        r"tôi\s+muốn\s+hỏi\s+(vài\s+điều|chút|đôi\s+điều|một\s+chút)",
        r"(cho|để)\s+(tôi|mình|em)\s+hỏi(\s+(chút|được|vài\s+điều))?",
        r"hỏi\s+(vài\s+điều|chút|đôi\s+điều|bạn\s+chút|tí|tý)",
        r"mình\s+hỏi\s+(chút|tí|tý|vài\s+điều)",
        r"(có\s+)?(được|được\s+không)\s+(hỏi|hỏi\s+bạn)\s*[?？]?",
    )
    if any(re.search(p, low) for p in patterns):
        return True
    if len(low) <= 36 and re.search(r"^(được\s+không|được\s+k|có\s+được\s+không)\s*[?？]?\s*$", low):
        return True
    return False


def _parse_branch_name_only(content: str) -> tuple[str, str]:
    """
    NeMo router: model trả **chỉ tên nhánh**. Lấy dòng đầu, chuẩn hoá; reason cố định ngắn.
    """
    text = (content or "").strip()
    if not text:
        raise ValueError("router: rỗng")
    if text.startswith("```"):
        text = re.sub(r"^```\w*\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text).strip()
    first = text.splitlines()[0].strip()
    first = re.sub(r"^[\s\"'`]+|[\s\"'`]+$", "", first)
    token = first.split()[0].lower().strip(".,;:!?。…")
    if token == _LEGACY_DIRECT:
        token = "graphrag"
    if token not in ALLOWED_ROUTES:
        raise ValueError(f"router: tên nhánh không hợp lệ: {token!r}")
    return token, f"branch={token}"


def _parse_router_json(content: str) -> tuple[str, str]:
    """Fallback nếu model vẫn trả JSON (tương thích bản router cũ)."""
    text = (content or "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    route = str(data.get("route") or "").strip().lower()
    reason = str(data.get("reason") or "").strip() or "(không có lý do từ model)"
    if route == _LEGACY_DIRECT:
        route = "graphrag"
        reason = f"{reason} (direct→graphrag)"
    if route not in ALLOWED_ROUTES:
        raise ValueError(f"route không hợp lệ: {data.get('route')!r}")
    return route, reason


def _parse_route_from_llm_output(content: str) -> tuple[str, str]:
    try:
        return _parse_branch_name_only(content)
    except ValueError:
        return _parse_router_json(content)


def _build_router_prompt_neomo_style(question: str) -> str:
    """Một user message: system + user gộp (Ollama /api/chat một message) — cùng ý với NeMo SYSTEM+USER."""
    branches_block = _branch_catalog_text()
    names = _branch_names_csv()
    return (
        "Bạn là Router Agent: **chỉ chọn nhánh**, không trả lời nội dung y khoa.\n\n"
        "Các nhánh khả dụng (mỗi dòng: tên + khi nào dùng — tương tự mô tả tool trong hệ thống agent):\n"
        f"{branches_block}\n\n"
        "QUY TẮC (giống cấu hình router một-pass):\n"
        f"- Phân tích tin nhắn người dùng.\n"
        f"- Chọn **đúng một** nhánh trong: [{names}]\n"
        "- Trả lời **chỉ** tên nhánh trên một dòng, không giải thích, không JSON, không markdown.\n"
        "- Nếu vừa xã giao vừa hỏi y tế → ưu tiên graphrag.\n\n"
        "Ví dụ:\n"
        "User: Xin chào!\n"
        "social\n\n"
        "User: Tác dụng paracetamol?\n"
        "graphrag\n\n"
        "User: Cho tôi hỏi chút được không?\n"
        "social\n\n"
        f"Tin nhắn:\n{question.strip()}\n"
    )


def _llm_route_plan(
    question: str,
    *,
    router_model: str,
    ollama_host: str,
    ollama_timeout: int,
    max_router_retries: int = DEFAULT_ROUTER_RETRIES,
) -> RetrievalPlan:
    q = (question or "").strip()
    prompt = _build_router_prompt_neomo_style(q)
    url = ollama_host.rstrip("/") + "/api/chat"
    payload = {
        "model": router_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0},
    }
    last_err: Exception | None = None
    for _ in range(max(1, max_router_retries)):
        resp = requests.post(url, json=payload, timeout=ollama_timeout)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        try:
            route, reason = _parse_route_from_llm_output(content)
        except (ValueError, json.JSONDecodeError, TypeError, KeyError) as exc:
            last_err = exc
            continue
        use_gr = route == "graphrag"
        return RetrievalPlan(
            use_gr,
            "router-llm: " + reason,
            router_route=route,
            next_pipeline=_next_pipeline(route),
        )
    if last_err is not None:
        raise last_err
    raise ValueError("router: không chọn được nhánh sau các lần thử")


def plan_retrieval(
    question: str,
    strategy: str = "auto",
    *,
    ollama_model: str | None = None,
    router_model: str | None = None,
    ollama_host: str | None = None,
    ollama_timeout: int = 120,
) -> RetrievalPlan:
    settings = get_settings()
    # Use OLLAMA_MODEL and OLLAMA_HOST from env/settings if not explicitly provided
    _ = ollama_model or settings.ollama.model
    host = ollama_host or settings.ollama.host
    s = (strategy or "auto").strip().lower()
    q = (question or "").strip()

    if s == "graph":
        return RetrievalPlan(
            True,
            "strategy=graph → nhánh graphrag (luôn gọi tool GraphRAG)",
            router_route="graphrag",
            next_pipeline="rag_llm",
        )

    if s != "auto":
        return RetrievalPlan(
            True,
            f"strategy={s!r} → graphrag",
            router_route="graphrag",
            next_pipeline="rag_llm",
        )

    if _router_heuristics_enabled():
        if is_obvious_pure_social(q):
            return RetrievalPlan(
                False,
                "heuristic: chào hỏi ngắn → nhánh social (không gọi tool)",
                router_route="social",
                next_pipeline="social_llm",
            )

        if is_meta_conversational_opener(q):
            return RetrievalPlan(
                False,
                "heuristic: xin phép hỏi → nhánh social (không gọi tool)",
                router_route="social",
                next_pipeline="social_llm",
            )

    try:
        return _llm_route_plan(
            q,
            router_model=router_model or DEFAULT_ROUTER_MODEL,
            ollama_host=host,
            ollama_timeout=ollama_timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return RetrievalPlan(
            True,
            f"llm-router lỗi → graphrag: {exc}",
            router_route="graphrag",
            next_pipeline="rag_llm",
        )
