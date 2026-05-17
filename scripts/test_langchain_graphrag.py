"""Test script for LangChain GraphRAG integration.

Usage:
    python scripts/test_langchain_graphrag.py "Tôi bị sốt và đau đầu là bệnh gì?"
    python scripts/test_langchain_graphrag.py "Thuốc paracetamol dùng để làm gì?"
"""

from __future__ import annotations

import asyncio
import sys


def test_langchain_graphrag_direct(question: str) -> None:
    """Test the LangChain GraphRAG module directly."""
    print(f"\n{'='*60}")
    print(f"Testing LangChain GraphRAG")
    print(f"Question: {question}")
    print(f"{'='*60}\n")

    # Test 1: Context retrieval
    print("[1] Testing context retrieval...")
    from llm_pipeline.langchain_graphrag import retrieve_langchain_graph_context

    context, sources = retrieve_langchain_graph_context(question)
    print(f"Sources found: {len(sources)}")
    for s in sources[:5]:
        print(f"  - {s['title']} ({s['source']})")
    print(f"\nContext preview (first 300 chars):\n{context[:300]}...")

    # Test 2: Full query with synthesis
    print(f"\n{'='*60}")
    print("[2] Testing full query with LLM synthesis...")
    print(f"{'='*60}\n")

    from llm_pipeline.langchain_graphrag import run_langchain_graphrag_query

    answer = run_langchain_graphrag_query(question)
    print(f"Answer:\n{answer}\n")


async def test_via_service(question: str) -> None:
    """Test via RetrievalService (async)."""
    print(f"\n{'='*60}")
    print("[3] Testing via RetrievalService")
    print(f"{'='*60}\n")

    from services.retrieval_service import RetrievalService

    service = RetrievalService()

    # Test query with sources
    answer, sources = await service.query_langchain_graph_with_sources(question)
    print(f"Answer: {answer}")
    print(f"\nSources: {len(sources)}")
    for s in sources:
        print(f"  - {s.get('title')} ({s.get('source')})")


def test_direct_query_no_llm(question: str) -> None:
    """Test direct query without LLM synthesis."""
    print(f"\n{'='*60}")
    print("[4] Testing DIRECT query (NO LLM - raw context only)")
    print(f"{'='*60}\n")

    from llm_pipeline.langchain_graphrag import run_langchain_graphrag_query_direct

    raw_context, sources = run_langchain_graphrag_query_direct(question)
    
    print(f"Sources found: {len(sources)}")
    for s in sources[:5]:
        print(f"  - {s['title']} ({s['source']})")
    
    print(f"\n=== RAW CONTEXT (first 800 chars) ===\n")
    print(raw_context[:800] + "..." if len(raw_context) > 800 else raw_context)
    print(f"\n[Tổng độ dài context: {len(raw_context)} ký tự]")


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        question = "Tôi bị sốt và đau đầu là bệnh gì?"
    else:
        question = " ".join(sys.argv[1:])

    try:
        # Test direct module with LLM
        test_langchain_graphrag_direct(question)

        # Test via service (async)
        print("\n")
        asyncio.run(test_via_service(question))
        
        # Test direct query without LLM
        test_direct_query_no_llm(question)

        print(f"\n{'='*60}")
        print("✓ All tests passed!")
        print(f"{'='*60}\n")
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
