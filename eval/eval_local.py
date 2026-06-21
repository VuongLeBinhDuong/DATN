"""Local Offline NLP Evaluation Benchmark for GraphRAG CDSS.

Usage:
    python eval/eval_local.py --dataset eval/ragas_test_queries.jsonl --out eval/local_eval_report.md
    python eval/eval_local.py --limit 3  # Quick test with 3 samples
"""

from __future__ import annotations

import argparse
import json
import os
import sys
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

# Global variables
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Local Offline Evaluation for GraphRAG CDSS")
    ap.add_argument("--dataset", default="eval/ragas_test_queries.jsonl", help="Đường dẫn file test dataset")
    ap.add_argument("--out", default="eval/local_eval_report.md", help="Đường dẫn xuất file báo cáo")
    ap.add_argument("--limit", type=int, default=0, help="Giới hạn số mẫu chạy thử nghiệm nhanh")
    ap.add_argument("--pipeline", default="graphrag", choices=["graphrag", "agent"], help="Pipeline chạy thử nghiệm (truy vấn GraphRAG trực tiếp hoặc chạy qua ReAct Agent)")
    args = ap.parse_args()

    print(f"=== Khởi động Đánh giá NLP Cục bộ (Pipeline: {args.pipeline.upper()}) ===")
    
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
        from retrieval.graph_first import graph_first_retrieve
        if args.pipeline == "graphrag":
            from llm_pipeline.graphrag_query import run_graphrag_query_with_sources
        else:
            from agent.react.agent import run_react_agent
    except ImportError as e:
        print(f"Lỗi import pipeline dự án: {e}")
        return 1

    eval_results = []
    print("\nBắt đầu chạy thử nghiệm qua hệ thống...")
    for i, item in enumerate(queries, 1):
        question = item["question"]
        ground_truth = item.get("ground_truth", "")
        print(f"[{i}/{len(queries)}] Đang xử lý: {question[:50]}...")
        
        # 1. Retrieval
        try:
            ret_result = graph_first_retrieve(question)
            contexts = [ch.get("text", "") for ch in getattr(ret_result, "evidence_chunks", [])]
        except Exception as e:
            print(f"  ⚠ Lỗi truy xuất: {e}")
            contexts = []

        # 2. Generation
        agent_steps_count = 0
        agent_errors_count = 0
        loop_guard_triggered = False
        agent_success = True
        
        try:
            if args.pipeline == "graphrag":
                answer, _ = run_graphrag_query_with_sources(question)
            else:
                agent_res = run_react_agent(question)
                answer = agent_res.get("answer", "")
                
                # Extract agent-specific metrics
                steps = agent_res.get("plan", {}).get("steps", [])
                agent_steps_count = len(steps)
                agent_errors_count = len(agent_res.get("errors", []))
                loop_guard_triggered = any(s.get("type") == "finish_loop_guard" for s in steps)
                # Success means it parsed correctly and resolved with a finish step
                agent_success = not any("react-parse" in err for err in agent_res.get("errors", []))
        except Exception as e:
            print(f"  ⚠ Lỗi sinh câu trả lời: {e}")
            answer = ""
            agent_success = False

        # 3. Calculate NLP metrics locally
        similarity = calculate_semantic_similarity(answer, ground_truth)
        rouge_l = calculate_rouge_l(answer, ground_truth)
        bleu_4 = calculate_bleu_4(answer, ground_truth)

        eval_results.append({
            "question": question,
            "contexts": contexts,
            "answer": answer,
            "ground_truth": ground_truth,
            "similarity": similarity,
            "rouge_l": rouge_l,
            "bleu_4": bleu_4,
            "agent_steps": agent_steps_count,
            "agent_errors": agent_errors_count,
            "loop_guard_triggered": loop_guard_triggered,
            "agent_success": agent_success
        })

    # Summary calculations
    avg_similarity = sum(r["similarity"] for r in eval_results) / len(eval_results)
    avg_rouge = sum(r["rouge_l"] for r in eval_results) / len(eval_results)
    avg_bleu = sum(r["bleu_4"] for r in eval_results) / len(eval_results)

    print("\n=== Kết quả Đánh giá Tổng quan Cục bộ ===")
    print(f"- SBERT Semantic Similarity: {avg_similarity:.4f}")
    print(f"- ROUGE-L (LCS Token F1):    {avg_rouge:.4f}")
    print(f"- BLEU-4 Score:              {avg_bleu:.4f}")

    if args.pipeline == "agent":
        avg_steps = sum(r["agent_steps"] for r in eval_results) / len(eval_results)
        total_parse_errors = sum(1 for r in eval_results if not r["agent_success"])
        total_loop_guards = sum(1 for r in eval_results if r["loop_guard_triggered"])
        agent_success_rate = sum(1 for r in eval_results if r["agent_success"]) / len(eval_results)
        
        print("\n=== Chỉ số Tác tử (Agent Metrics) ===")
        print(f"- Số bước suy luận TB (Avg Steps):    {avg_steps:.2f}")
        print(f"- Tỷ lệ thành công (Success Rate):    {agent_success_rate * 100:.1f}%")
        print(f"- Tổng số lỗi phân tích cú pháp:      {total_parse_errors}")
        print(f"- Số lần kích hoạt Loop Guard:        {total_loop_guards}")

    # Generate Markdown Report
    report_lines = [
        f"# Báo cáo Đánh giá RAG Cục bộ (Pipeline: {args.pipeline.upper()})",
        "",
        f"**Tổng số câu hỏi kiểm thử:** {len(queries)}",
        f"**Định dạng:** 100% Offline (Không phụ thuộc LLM ngoài)",
        "",
        "## Chỉ số Trung bình (Aggregate Metrics)",
        "",
        "| Chỉ số | Điểm số | Ý nghĩa đánh giá |",
        "| :--- | :--- | :--- |",
        f"| **SBERT Similarity** | {avg_similarity:.4f} | Độ tương đồng ngữ nghĩa của câu trả lời sinh ra so với đáp án chuẩn |",
        f"| **ROUGE-L** | {avg_rouge:.4f} | Mức độ giữ chuỗi con chung dài nhất (đo độ phủ thông tin từ vựng) |",
        f"| **BLEU-4** | {avg_bleu:.4f} | Tỷ lệ trùng khớp các cụm từ (đo độ tự nhiên của câu chữ) |",
    ]

    if args.pipeline == "agent":
        report_lines.extend([
            "",
            "## Chỉ số Tác tử (Agent Metrics)",
            "",
            "| Chỉ số Tác tử | Điểm số / Thống kê | Ý nghĩa y khoa / kỹ thuật |",
            "| :--- | :--- | :--- |",
            f"| **Số bước lập luận trung bình** | {avg_steps:.2f} | Số lần tác tử gọi công cụ tra cứu trước khi kết luận |",
            f"| **Tỷ lệ Agent thành công** | {agent_success_rate * 100:.1f}% | Tỷ lệ Agent kết luận thành công không bị lỗi cú pháp |",
            f"| **Tổng số lỗi Parse định dạng** | {total_parse_errors} | Số lần mô hình sinh sai cú pháp `Thought/Action` |",
            f"| **Số lần kích hoạt Loop Guard** | {total_loop_guards} | Số lần chặn vòng lặp vô hạn (lặp câu hỏi tra cứu) |",
        ])

    report_lines.extend([
        "",
        "## Chi tiết từng câu hỏi (Detailed Results)",
        ""
    ])

    for i, item in enumerate(eval_results):
        report_lines.extend([
            f"### Câu {i+1}: {item['question']}",
            "",
            f"**Chỉ số đo đạc:**",
            f"- Semantic Similarity: **{item['similarity']:.4f}**",
            f"- ROUGE-L: **{item['rouge_l']:.4f}**",
            f"- BLEU-4: **{item['bleu_4']:.4f}**",
        ])
        
        if args.pipeline == "agent":
            report_lines.extend([
                f"- Số bước lập luận: **{item['agent_steps']}**",
                f"- Trạng thái Parse thành công: **{item['agent_success']}**",
                f"- Bị Loop Guard chặn: **{item['loop_guard_triggered']}**",
            ])
            
        report_lines.extend([
            "",
            f"**Ngữ cảnh truy xuất (Contexts):**",
            *[f"- {ctx[:120]}..." for ctx in item["contexts"][:3]],
            "",
            f"**Đáp án chuẩn (Ground Truth):**",
            f"> {item['ground_truth']}",
            "",
            f"**Hệ thống trả lời (Generated Answer):**",
            f"> {item['answer']}",
            "",
            "---",
            ""
        ])

    # Write report
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n✓ Đã kết xuất báo cáo thành công tại: {out_path.absolute()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
