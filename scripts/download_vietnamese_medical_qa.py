"""Download and extract a gold subset of the vietnamese-medical-qa benchmark.

Saves the benchmark subset to eval/vietnamese_medical_qa_gold.jsonl
"""

import json
import sys
from pathlib import Path
from datasets import load_dataset

# Ensure standard output uses UTF-8 to prevent CP1252/UnicodeEncodeError on Windows
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

OUTPUT_PATH = Path("eval/vietnamese_medical_qa_gold.jsonl")

def main():
    print("✓ Đang tải bộ dữ liệu 'hungnm/vietnamese-medical-qa' từ Hugging Face...")
    try:
        dataset = load_dataset("hungnm/vietnamese-medical-qa", split="train")
    except Exception as e:
        print(f"⚠ Lỗi tải dataset: {e}")
        return 1

    print(f"Tổng số mẫu trong dataset gốc: {len(dataset)}")
    
    # Lọc ra các câu hỏi và câu trả lời chất lượng (không quá ngắn, không quá dài)
    selected_samples = []
    for item in dataset:
        q = item.get("question", "").strip()
        a = item.get("answer", "").strip()
        
        # Chỉ lấy các câu hỏi có độ dài từ 15 đến 120 từ, câu trả lời từ 30 đến 250 từ
        q_len = len(q.split())
        a_len = len(a.split())
        
        if 15 <= q_len <= 120 and 30 <= a_len <= 250:
            selected_samples.append({
                "question": q,
                "ground_truth": a
            })
            
        if len(selected_samples) >= 30: # Lấy 30 câu mẫu chuẩn
            break

    # Ghi ra file JSONL
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for sample in selected_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            
    print(f"✓ Đã lưu thành công {len(selected_samples)} câu hỏi chuẩn y khoa tại: {OUTPUT_PATH.absolute()}")
    return 0

if __name__ == "__main__":
    exit(main())
