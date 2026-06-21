"""Comparative Local Evaluation: Pure LLM vs. GraphRAG.

Usage:
    python eval/eval_comparison.py --dataset eval/vietnamese_medical_qa_gold.jsonl --out eval/system_comparison_report.md
    python eval/eval_comparison.py --limit 3  # Test with 3 samples
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure standard output uses UTF-8 to prevent CP1252/UnicodeEncodeError on Windows
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Load environment
from dotenv import load_dotenv
load_dotenv(REPO_ROOT / "config" / ".env")
load_dotenv(REPO_ROOT / ".env")

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
import nltk
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction

# Ensure nltk packages are downloaded locally silently
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

# Global SBERT model
_sbert_model = None


def get_sbert_model() -> SentenceTransformer:
    """Lazy load SentenceTransformer model."""
    global _sbert_model
    if _sbert_model is None:
        model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        print(f"✓ Loading SentenceTransformer: {model_name}...")
        _sbert_model = SentenceTransformer(model_name)
    return _sbert_model


def calculate_semantic_similarity(candidate: str, reference: str) -> float:
    """Calculate Cosine Similarity of SBERT embeddings."""
    if not candidate.strip() or not reference.strip():
        return 0.0
    try:
        model = get_sbert_model()
        embs = model.encode([candidate, reference])
        vec1, vec2 = embs[0], embs[1]
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))
    except Exception as e:
        print(f"  ⚠ Error encoding/similarity: {e}")
        return 0.0


def compute_lcs(x: list[str], y: list[str]) -> int:
    """Calculate Longest Common Subsequence length."""
    m, n = len(x), len(y)
    L = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        for j in range(n + 1):
            if i == 0 or j == 0:
                L[i][j] = 0
            elif x[i-1] == y[j-1]:
                L[i][j] = L[i-1][j-1] + 1
            else:
                L[i][j] = max(L[i-1][j], L[i][j-1])
    return L[m][n]


def calculate_rouge_l(candidate: str, reference: str) -> float:
    """Calculate ROUGE-L F1-score (LCS-based token overlap)."""
    cand_tokens = candidate.lower().split()
    ref_tokens = reference.lower().split()
    if not cand_tokens or not ref_tokens:
        return 0.0
    lcs_len = compute_lcs(cand_tokens, ref_tokens)
    precision = lcs_len / len(cand_tokens)
    recall = lcs_len / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def calculate_bleu_4(candidate: str, reference: str) -> float:
    """Calculate BLEU-4 score using NLTK sentence_bleu and smoothing."""
    cand_tokens = candidate.lower().split()
    ref_tokens = [reference.lower().split()]
    if not cand_tokens or not ref_tokens[0]:
        return 0.0
    smooth = SmoothingFunction().method1
    try:
        return float(sentence_bleu(ref_tokens, cand_tokens, smoothing_function=smooth))
    except Exception:
        return 0.0


def load_queries(dataset_path: str, limit: int = 0) -> list[dict[str, Any]]:
    """Load test queries from JSONL."""
    queries = []
    p = Path(dataset_path)
    if not p.exists():
        print(f"⚠ Không tìm thấy file dữ liệu test: {dataset_path}")
        return []
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))
    if limit > 0:
        queries = queries[:limit]
    return queries


def run_pure_llm_query(question: str) -> str:
    """Query local Ollama directly without any RAG context."""
    from llm_pipeline.llm_chat import chat_ollama
    
    # Standard medical context instruction for pure LLM evaluation
    prompt = (
        "Bạn là một trợ lý ảo y tế thông minh. Hãy trả lời câu hỏi dưới đây của người bệnh bằng tiếng Việt một cách khoa học, cẩn trọng.\n\n"
        f"Câu hỏi: {question}\n"
    )
    
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    try:
        return chat_ollama(
            prompt,
            host=host,
            model=model,
            temperature=0.2,
            num_predict=1024
        )
    except Exception as e:
        return f"Lỗi gọi LLM trực tiếp: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Comparative Evaluation: Pure LLM vs. GraphRAG")
    ap.add_argument("--dataset", default="eval/vietnamese_medical_qa_gold.jsonl", help="Đường dẫn file test dataset")
    ap.add_argument("--out", default="eval/system_comparison_report.md", help="Đường dẫn xuất file báo cáo")
    ap.add_argument("--limit", type=int, default=0, help="Giới hạn số mẫu chạy thử nghiệm nhanh")
    args = ap.parse_args()

    print("=== Khởi động Đánh giá Đối chiếu: Pure LLM vs. GraphRAG ===")
    
    # Load Neo4j config and inject credentials into environment variables
    try:
        from llm_pipeline.neo4j_graphrag import load_neo4j_config
        neo_cfg = load_neo4j_config()
        if neo_cfg:
            os.environ["NEO4J_URI"] = neo_cfg.get("uri", "")
            os.environ["NEO4J_USER"] = neo_cfg.get("user", "")
            os.environ["NEO4J_PASSWORD"] = neo_cfg.get("password", "")
            os.environ["NEO4J_DATABASE"] = neo_cfg.get("database") or "neo4j"
    except Exception as e:
        print(f"⚠ Lỗi load cấu hình Neo4j: {e}")

    queries = load_queries(args.dataset, args.limit)
    if not queries:
        print("Không có câu hỏi nào để đánh giá.")
        return 1
    print(f"Đã nạp {len(queries)} câu hỏi từ {args.dataset}")

    # Import project modules
    try:
        from llm_pipeline.graphrag_query import run_graphrag_query_with_sources
    except ImportError as e:
        print(f"Lỗi import pipeline dự án: {e}")
        return 1

    eval_results = []
    print("\nBắt đầu chạy thử nghiệm qua cả hai hệ thống...")
    for i, item in enumerate(queries, 1):
        question = item["question"]
        ground_truth = item.get("ground_truth", "")
        print(f"[{i}/{len(queries)}] Đang xử lý: {question[:50]}...")
        
        # 1. Chạy Pure LLM (Không RAG)
        t0 = time.perf_counter()
        pure_answer = run_pure_llm_query(question)
        pure_latency = time.perf_counter() - t0

        # 2. Chạy GraphRAG
        t0 = time.perf_counter()
        try:
            graphrag_answer, _ = run_graphrag_query_with_sources(question)
        except Exception as e:
            graphrag_answer = f"Lỗi GraphRAG: {e}"
        gr_latency = time.perf_counter() - t0

        # 3. Tính toán các chỉ số cho cả hai bên
        pure_sim = calculate_semantic_similarity(pure_answer, ground_truth)
        pure_rouge = calculate_rouge_l(pure_answer, ground_truth)
        pure_bleu = calculate_bleu_4(pure_answer, ground_truth)

        gr_sim = calculate_semantic_similarity(graphrag_answer, ground_truth)
        gr_rouge = calculate_rouge_l(graphrag_answer, ground_truth)
        gr_bleu = calculate_bleu_4(graphrag_answer, ground_truth)

        eval_results.append({
            "question": question,
            "ground_truth": ground_truth,
            "pure_answer": pure_answer,
            "graphrag_answer": graphrag_answer,
            "pure_metrics": {"similarity": pure_sim, "rouge_l": pure_rouge, "bleu_4": pure_bleu, "latency": pure_latency},
            "graphrag_metrics": {"similarity": gr_sim, "rouge_l": gr_rouge, "bleu_4": gr_bleu, "latency": gr_latency}
        })

    # Tính trung bình chung
    avg_pure_sim = sum(r["pure_metrics"]["similarity"] for r in eval_results) / len(eval_results)
    avg_pure_rouge = sum(r["pure_metrics"]["rouge_l"] for r in eval_results) / len(eval_results)
    avg_pure_bleu = sum(r["pure_metrics"]["bleu_4"] for r in eval_results) / len(eval_results)
    avg_pure_latency = sum(r["pure_metrics"]["latency"] for r in eval_results) / len(eval_results)

    avg_gr_sim = sum(r["graphrag_metrics"]["similarity"] for r in eval_results) / len(eval_results)
    avg_gr_rouge = sum(r["graphrag_metrics"]["rouge_l"] for r in eval_results) / len(eval_results)
    avg_gr_bleu = sum(r["graphrag_metrics"]["bleu_4"] for r in eval_results) / len(eval_results)
    avg_gr_latency = sum(r["graphrag_metrics"]["latency"] for r in eval_results) / len(eval_results)

    # Hiển thị bảng so khớp trên terminal
    print("\n=== KẾT QUẢ SO SÁNH ĐỐI CHIẾU ===")
    print(f"Chỉ số                  | Pure LLM (Baseline) | GraphRAG (Hệ thống) | Chênh lệch (Delta)")
    print(f"------------------------+---------------------+---------------------+-------------------")
    print(f"SBERT Similarity        | {avg_pure_sim:.4f}              | {avg_gr_sim:.4f}              | {avg_gr_sim - avg_pure_sim:+.4f}")
    print(f"ROUGE-L                 | {avg_pure_rouge:.4f}              | {avg_gr_rouge:.4f}              | {avg_gr_rouge - avg_pure_rouge:+.4f}")
    print(f"BLEU-4                  | {avg_pure_bleu:.4f}              | {avg_gr_bleu:.4f}              | {avg_gr_bleu - avg_pure_bleu:+.4f}")
    print(f"Độ trễ TB (Latency)      | {avg_pure_latency:.2f}s             | {avg_gr_latency:.2f}s             | {avg_gr_latency - avg_pure_latency:+.2fs}")

    # Tạo báo cáo Markdown chi tiết
    report_lines = [
        "# Báo cáo So sánh Đối chiếu: Pure LLM vs. GraphRAG",
        "",
        f"**Tổng số câu hỏi đánh giá:** {len(queries)}",
        f"**Mô hình LLM:** {os.getenv('OLLAMA_MODEL', 'llama3.1:8b')}",
        "",
        "## 1. Bảng So sánh Chỉ số Trung bình (Aggregate Comparison)",
        "",
        "| Chỉ số NLP | Pure LLM (Baseline) | GraphRAG (Hệ thống) | Chênh lệch (Delta) | Ý nghĩa đánh giá |",
        "| :--- | :---: | :---: | :---: | :--- |",
        f"| **SBERT Similarity** | {avg_pure_sim:.4f} | {avg_gr_sim:.4f} | {avg_gr_sim - avg_pure_sim:+.4f} | Độ tương đồng ngữ nghĩa y học (Cosine) |",
        f"| **ROUGE-L** | {avg_pure_rouge:.4f} | {avg_gr_rouge:.4f} | {avg_gr_rouge - avg_pure_rouge:+.4f} | Khả năng bao phủ từ khóa y khoa (LCS) |",
        f"| **BLEU-4** | {avg_pure_bleu:.4f} | {avg_gr_bleu:.4f} | {avg_gr_bleu - avg_pure_bleu:+.4f} | Tỷ lệ trùng khớp cụm từ tự nhiên |",
        f"| **Độ trễ trung bình** | {avg_pure_latency:.2f}s | {avg_gr_latency:.2f}s | {avg_gr_latency - avg_pure_latency:+.2f}s | Tốc độ xử lý trung bình mỗi câu |",
        "",
        "## 2. Chi tiết từng câu hỏi (Detailed Side-by-Side Results)",
        ""
    ]

    for i, item in enumerate(eval_results):
        pm = item["pure_metrics"]
        gm = item["graphrag_metrics"]
        report_lines.extend([
            f"### Câu {i+1}: {item['question']}",
            "",
            "| Hệ thống | SBERT Similarity | ROUGE-L | BLEU-4 | Độ trễ |",
            "| :--- | :---: | :---: | :---: | :---: |",
            f"| **Pure LLM** | {pm['similarity']:.4f} | {pm['rouge_l']:.4f} | {pm['bleu_4']:.4f} | {pm['latency']:.2f}s |",
            f"| **GraphRAG** | {gm['similarity']:.4f} | {gm['rouge_l']:.4f} | {gm['bleu_4']:.4f} | {gm['latency']:.2f}s |",
            "",
            "#### ⬜ Đáp án chuẩn (Ground Truth)",
            f"> {item['ground_truth']}",
            "",
            "<details>",
            "<summary>🔍 Xem chi tiết câu trả lời của hai hệ thống</summary>",
            "",
            "##### 🟦 Câu trả lời của Pure LLM (LLM không dùng RAG)",
            item["pure_answer"],
            "",
            "##### 🟩 Câu trả lời của GraphRAG (LLM tích hợp Đồ thị Tri thức)",
            item["graphrag_answer"],
            "",
            "</details>",
            "",
            "---",
            ""
        ])

    # Ghi file
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n✓ Báo cáo so sánh đối chiếu đã xuất thành công tại: {out_path.absolute()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
