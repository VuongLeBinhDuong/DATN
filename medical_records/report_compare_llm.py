"""LLM reads extracted report text and compares each test's result to reference AS PRINTED on the form."""

from __future__ import annotations

import os
from typing import Any

import requests

# Avoid huge prompts; full typical lab PDF text fits; tune via env.
_MAX_CHARS = int(os.getenv("MEDICAL_RECORD_REPORT_LLM_MAX_CHARS", "14000"))


def llm_compare_result_to_reference_on_report(
    extracted_text: str,
    *,
    language: str = "vi",
) -> str | None:
    """
    Grounded comparison: model must use ONLY the pasted report text.
    Output language: Vietnamese by default (for end users in Vietnam).
    """
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    timeout = int(os.getenv("OLLAMA_TIMEOUT", "180"))
    body = (extracted_text or "")[:_MAX_CHARS]
    if len(extracted_text or "") > _MAX_CHARS:
        body += "\n\n[... truncated for model context; full text available upstream.]"

    lang_note = (
        "Trả lời bằng tiếng Việt rõ ràng, dễ hiểu với người bệnh."
        if language.lower().startswith("vi")
        else "Answer in clear English suitable for a layperson."
    )

    prompt = f"""Bạn là trợ lý thông tin y tế. Tránh chẩn đoán dứt khoát cho cá nhân chỉ từ phiếu; sau khi so sánh chỉ số, có thể gợi ý thuốc điều trị phù hợp (tên, liều tham khảo) khi thích hợp.

Nhiệm vụ: Đọc CHỈ đoạn văn bản phiếu xét nghiệm dưới đây (đã trích từ file). Trên phiếu thường có cột/bộ phận tương ứng: tên xét nghiệm, KẾT QUẢ của người bệnh, và GIÁ TRỊ THAM CHIẾU / KHOẢNG BÌNH THƯỜNG do phòng lab in sẵn.

{lang_note}

Quy tắc cứng:
1) Chỉ được suy luận từ chữ trong khối "PHIẾU" bên dưới. Không dùng kiến thức bên ngoài để sửa số hay đổi khoảng tham chiếu.
2) Với mỗi xét nghiệm mà bạn đọc được CẢ kết quả VÀ tham chiếu trên phiếu: nêu ngắn gọn là bình thường / cao hơn / thấp hơn / không so được (ví dụ xét nghiệm định tính, hoặc thiếu số).
3) Phần "có thể liên quan đến những nguyên nhân gì" chỉ mang tính giáo dục phổ biến — KHÔNG kết luận nguyên nhân cho riêng bệnh nhân này.

Cấu trúc gợi ý (markdown):
- Tóm tắt phiếu (loại mẫu, ngày nếu có trong text).
- Bảng hoặc danh sách: Tên XN | Kết quả (theo phiếu) | Tham chiếu (theo phiếu) | Nhận xét nhanh.
- Các chỉ số lệch tham chiếu in trên phiếu (nếu có): gợi ý hướng tìm hiểu thêm (không chẩn đoán).
- Điều không chắc / thiếu dữ liệu trong text.
- Điểm cần lưu ý từ dữ liệu trên phiếu; nếu có chỉ số lệch, có thể thêm mục gợi ý thuốc/lối sống phù hợp.

--- BẮT ĐẦU PHIẾU (chỉ dùng nội dung này) ---
{body}
--- KẾT THÚC PHIẾU ---"""

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
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": 0.15,
                "num_ctx": num_ctx,
            },
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("message", {}) or {}).get("content", "").strip() or None
    except requests.RequestException:
        return None


def call_report_compare(
    extracted_text: str,
    *,
    language: str = "vi",
) -> dict[str, Any]:
    """Returns dict with text or error hint for API."""
    text = llm_compare_result_to_reference_on_report(extracted_text, language=language)
    return {"narrative_report_compare": text, "report_compare_used_chars": min(len(extracted_text or ""), _MAX_CHARS)}
