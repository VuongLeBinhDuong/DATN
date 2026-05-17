# Module Prompts

## Mục đích

`prompts/` lưu các mẫu prompt dùng lúc chạy thật (runtime) cho các luồng trả lời khác nhau.

## Thành phần

| File | Vai trò |
|---|---|
| `agent_merged_context_prompt.txt` | Prompt hợp nhất nhiều nguồn context cho agent |
| `grounded_rag_prompt.txt` | Prompt yêu cầu trả lời bám nguồn retrieval |
| `direct_llm_prompt.txt` | Prompt cho chế độ gọi LLM trực tiếp |
| `social_turn_prompt.txt` | Prompt cho lượt hội thoại xã giao/chuyển ngữ cảnh |

## Ánh xạ tới code (basename)

Prompt được nạp qua helper trong `llm_pipeline/rag_llm.py` (`_read_prompt_file`) và hằng trong `rag_llm` / agent legacy (`DEFAULT_AGENT_MERGED_PROMPT`, `SOCIAL_TURN_PROMPT`, …). Khi đổi tên file `.txt`, cập nhật basename tham chiếu trong code tương ứng.

## Nguyên tắc chỉnh sửa prompt

1. Mỗi thay đổi prompt nên được test bằng bộ câu hỏi chuẩn.
2. Tránh thay đổi quá nhiều biến cùng lúc, khó đo tác động.
3. Gắn tag phiên bản prompt trong changelog nội bộ nếu có.

## Sơ đồ luồng prompt -> LLM

```text
prompts/*.txt -> _read_prompt_file -> llm_pipeline/rag_llm.py
                                         |
                                         +-> agent/orchestrator.py
                                         +-> Ollama/OpenRouter

agent/react/prompts.py -> ReActAgent -> Ollama/OpenRouter
```

## Cần cải thiện

1. Version hóa prompt theo thư mục con (`v1`, `v2`, ...).
2. Tự động A/B test prompt bằng script đánh giá.
3. Thêm guardrails prompt cho tình huống y khoa nhạy cảm.

## Liên kết

- README tổng: [`../README.md`](../README.md)
- Agent module: [`../agent/README.md`](../agent/README.md)
