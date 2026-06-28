"""Evaluate RAG pipeline quality using Ragas.

Usage:
    python eval/eval_ragas.py --dataset eval/ragas_test_queries.jsonl --out eval/ragas_report.md
    python eval/eval_ragas.py --limit 3  # Quick test with sample queries
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

# Load .env file
from dotenv import load_dotenv
load_dotenv(REPO_ROOT / "config" / ".env")
load_dotenv(REPO_ROOT / ".env")

try:
    import pandas as pd
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from langchain_openai import ChatOpenAI
    from langchain_community.embeddings import HuggingFaceEmbeddings
    RAGAS_AVAILABLE = True
except ImportError as e:
    RAGAS_AVAILABLE = False
    RAGAS_IMPORT_ERROR = str(e)


def load_queries(dataset_path: str, limit: int = 0) -> list[dict[str, Any]]:
    """Load test queries from JSONL file."""
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


def setup_evaluator_llm(evaluator_type: str) -> Any:
    """Setup LLM evaluator using Ollama, OpenRouter, or OpenAI."""
    evaluator_type = evaluator_type.lower()
    
    if evaluator_type == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print("⚠ Lỗi: Không tìm thấy OPENROUTER_API_KEY trong cấu hình.")
            return None
        model_name = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        print(f"✓ Sử dụng OpenRouter làm Giám khảo Ragas: Model={model_name}")
        
        # Set OPENAI_API_KEY env var to support internal packages checking for it
        os.environ["OPENAI_API_KEY"] = api_key
        
        llm = ChatOpenAI(
            model=model_name,
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_headers={
                "HTTP-Referer": "https://github.com/VuongLeBinhDuong/DATN",
                "X-Title": "DATN CDSS GraphRAG Evaluation"
            },
            temperature=0.0
        )
        return LangchainLLMWrapper(llm)
        
    elif evaluator_type == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("⚠ Lỗi: Không tìm thấy OPENAI_API_KEY trong cấu hình.")
            return None
        print("✓ Sử dụng OpenAI làm Giám khảo Ragas (gpt-4o-mini)")
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            openai_api_key=api_key,
            temperature=0.0
        )
        return LangchainLLMWrapper(llm)
        
    else:  # ollama
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        model_name = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        print(f"✓ Sử dụng Ollama làm Giám khảo Ragas: Model={model_name}, Host={host}")
        
        from langchain_community.chat_models import ChatOllama
        llm = ChatOllama(
            base_url=host,
            model=model_name,
            temperature=0.0
        )
        return LangchainLLMWrapper(llm)


def main() -> int:
    if not RAGAS_AVAILABLE:
        print("=== Lỗi import thư viện Ragas ===")
        print(f"Chi tiết: {RAGAS_IMPORT_ERROR}")
        print("\nVui lòng chạy lệnh sau để cài đặt các thư viện cần thiết:")
        print("  pip install ragas langchain-openai datasets pandas")
        return 1

    ap = argparse.ArgumentParser(description="Evaluate GraphRAG using Ragas")
    ap.add_argument("--dataset", default="eval/ragas_test_queries.jsonl", help="Đường dẫn đến file test dataset JSONL")
    ap.add_argument("--out", default="eval/ragas_report.md", help="Đường dẫn lưu báo cáo kết quả")
    ap.add_argument("--limit", type=int, default=0, help="Giới hạn số lượng câu hỏi để chạy thử nghiệm nhanh")
    ap.add_argument("--evaluator", default="ollama", choices=["ollama", "openrouter", "openai"], help="Mô hình LLM làm giám khảo đánh giá")
    args = ap.parse_args()

    print("=== Đánh giá chất lượng RAG bằng Ragas ===")
    
    # Load queries
    queries = load_queries(args.dataset, args.limit)
    if not queries:
        print("Không có câu hỏi nào để đánh giá.")
        return 1
    print(f"Đã nạp {len(queries)} câu hỏi từ {args.dataset}")

    # Import pipeline elements
    try:
        from retrieval.graph_first import graph_first_retrieve
        from llm_pipeline.graphrag_query import run_graphrag_query_with_sources
    except ImportError as e:
        print(f"Lỗi import pipeline dự án: {e}")
        return 1

    eval_data = []
    print("\nBắt đầu chạy thử nghiệm qua hệ thống...")
    for i, item in enumerate(queries, 1):
        question = item["question"]
        ground_truth = item.get("ground_truth", "")
        print(f"[{i}/{len(queries)}] Đang xử lý: {question[:50]}...")
        
        # 1. Chạy Retrieval lấy context
        try:
            ret_result = graph_first_retrieve(question)
            contexts = [ch.get("text", "") for ch in getattr(ret_result, "evidence_chunks", [])]
            # Đảm bảo có ít nhất 1 context để tránh lỗi Ragas
            if not contexts:
                contexts = ["(Không tìm thấy ngữ cảnh phù hợp từ Graph/Neo4j)"]
        except Exception as e:
            print(f"  ⚠ Lỗi truy xuất: {e}")
            contexts = [f"Lỗi truy xuất: {e}"]
            
        # 2. Sinh câu trả lời qua Agent/Synthesis LLM
        try:
            answer, _ = run_graphrag_query_with_sources(question)
        except Exception as e:
            print(f"  ⚠ Lỗi sinh câu trả lời: {e}")
            answer = f"Lỗi sinh câu trả lời: {e}"

        eval_data.append({
            "user_input": question,
            "retrieved_contexts": contexts,
            "response": answer,
            "reference": ground_truth
        })

    # Convert to HuggingFace Dataset
    df = pd.DataFrame(eval_data)
    dataset = Dataset.from_pandas(df)
    
    # Setup LLM Evaluator
    evaluator_llm = setup_evaluator_llm(args.evaluator)
    if evaluator_llm is None:
        print("Lỗi: Cấu hình giám khảo evaluator không hợp lệ hoặc thiếu API key.")
        return 1

    # Setup Embeddings Evaluator
    emb_model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    print(f"✓ Sử dụng Embedding Model cục bộ cho Ragas: {emb_model_name}")
    try:
        lc_embeddings = HuggingFaceEmbeddings(model_name=emb_model_name)
        evaluator_embeddings = LangchainEmbeddingsWrapper(lc_embeddings)
    except Exception as e:
        print(f"⚠ Lỗi tải Embedding Model cục bộ: {e}. Thử dùng model mặc định.")
        lc_embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        evaluator_embeddings = LangchainEmbeddingsWrapper(lc_embeddings)

    print("\nĐang gửi dữ liệu tới LLM Giám khảo để đánh giá Ragas...")
    
    try:
        # Run Ragas Evaluation
        result = evaluate(
            dataset=dataset,
            metrics=[Faithfulness(), AnswerRelevancy(), ContextPrecision(), ContextRecall()],
            llm=evaluator_llm,
            embeddings=evaluator_embeddings
        )
    except Exception as e:
        print(f"Lỗi khi chạy đánh giá Ragas: {e}")
        print("Gợi ý: Đảm bảo dịch vụ Ollama đang chạy (ollama serve) và mô hình đã được tải về local.")
        return 1

    # Print results summary
    print("\n=== Kết quả Đánh giá Tổng quan ===")
    scores_dict = {}
    for metric_name in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        try:
            score = result[metric_name]
            scores_dict[metric_name] = score if (score is not None and not pd.isna(score)) else 0.0
        except Exception:
            scores_dict[metric_name] = 0.0
            
    for metric_name, score in scores_dict.items():
        print(f"- {metric_name.capitalize()}: {score:.4f}")
        
    all_zeros = all(score == 0.0 for score in scores_dict.values())
    if all_zeros and args.evaluator == "ollama":
        print("\n⚠ Lưu ý: Tất cả các chỉ số trả về 0.0.")
        print("Các mô hình local LLM nhỏ (như Llama 3.1 8B) thường gặp khó khăn trong việc tuân thủ định dạng JSON phức tạp")
        print("yêu cầu bởi Ragas, dẫn đến lỗi phân tích cú pháp (parsing error) và nhận điểm mặc định 0.0.")
        print("Khuyến nghị: Sử dụng OpenRouter (mô hình 70B+) bằng cách chạy lệnh:")
        print("  python eval/eval_ragas.py --limit 3 --evaluator openrouter")

    # Generate Markdown Report
    report_lines = [
        "# Báo cáo Đánh giá RAG sử dụng Ragas",
        "",
        f"**Tổng số câu hỏi kiểm thử:** {len(queries)}",
        f"**Thời gian thực hiện:** 2026-06-20",
        "",
        "## Chỉ số Trung bình (Aggregate Metrics)",
        "",
        "| Chỉ số | Điểm số (0.0 - 1.0) | Ý nghĩa lâm sàng |",
        "| :--- | :--- | :--- |",
        f"| **Faithfulness** | {scores_dict['faithfulness']:.4f} | Độ trung thực của câu trả lời so với tài liệu y học (Tránh ảo tưởng) |",
        f"| **Answer Relevancy** | {scores_dict['answer_relevancy']:.4f} | Độ liên quan, trực diện của câu trả lời với câu hỏi lâm sàng |",
        f"| **Context Precision** | {scores_dict['context_precision']:.4f} | Độ chính xác của các đoạn văn bản y khoa được truy xuất |",
        f"| **Context Recall** | {scores_dict['context_recall']:.4f} | Độ đầy đủ của các tài liệu y học được truy xuất so với đáp án chuẩn |",
        "",
        "## Chi tiết từng câu hỏi (Detailed Results)",
        ""
    ]

    for i, item in enumerate(eval_data):
        report_lines.extend([
            f"### Câu {i+1}: {item['user_input']}",
            "",
            f"**Ngữ cảnh truy xuất (Contexts):**",
            *[f"- {ctx[:150]}..." for ctx in item["retrieved_contexts"]],
            "",
            f"**Đáp án chuẩn (Ground Truth):**",
            f"> {item['reference']}",
            "",
            f"**Hệ thống trả lời (Generated Answer):**",
            f"> {item['response']}",
            "",
            "---",
            ""
        ])

    # Write report file
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n✓ Báo cáo chi tiết đã được xuất ra: {out_path.absolute()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
