#!/usr/bin/env python3
"""CLI: python -m agent --question "..."""""

from __future__ import annotations

import argparse
import json
import os
import sys

from agent.orchestrator import run_agent_demo
from agent.langgraph_app import run_agent_demo_langgraph
from agent.react import run_react_agent
from agent.router import DEFAULT_ROUTER_MODEL


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mặc định: ReAct + graphrag_query. --legacy = pipeline router+orchestrator (cũ)."
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Pipeline cũ: router + orchestrator (social|graphrag), không ReAct.",
    )
    parser.add_argument(
        "--langgraph",
        action="store_true",
        help="Cùng với --legacy: chạy LangGraph thay vì orchestrator thuần.",
    )
    parser.add_argument(
        "--react",
        action="store_true",
        help="ReAct (mặc định đã bật). Giữ flag để tương thích script cũ.",
    )
    parser.add_argument("--question", "-q", required=True, help="User question")
    parser.add_argument(
        "--strategy",
        "-s",
        default="auto",
        choices=["auto", "graph"],
        help="auto = LLM router; graph = luôn tra GraphRAG",
    )
    parser.add_argument("--ollama-model", default=os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
    parser.add_argument(
        "--router-model",
        default=DEFAULT_ROUTER_MODEL,
        help=f"Model điều phối khi strategy=auto (mặc định {DEFAULT_ROUTER_MODEL})",
    )
    parser.add_argument("--ollama-host", default=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    parser.add_argument("--ollama-timeout", type=int, default=120)
    parser.add_argument("--json", action="store_true", help="Print full trace as JSON")
    args = parser.parse_args()

    if args.legacy:
        runner = run_agent_demo_langgraph if args.langgraph else run_agent_demo
        out = runner(
            args.question,
            strategy=args.strategy,
            ollama_model=args.ollama_model,
            router_model=(args.router_model or "").strip() or DEFAULT_ROUTER_MODEL,
            ollama_host=args.ollama_host,
            ollama_timeout=args.ollama_timeout,
        )
    else:
        out = run_react_agent(
            args.question,
            ollama_model=args.ollama_model,
            ollama_host=args.ollama_host,
            ollama_timeout=args.ollama_timeout,
        )

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print("=== Plan ===")
    print(json.dumps(out["plan"], ensure_ascii=False, indent=2))
    if out["errors"]:
        print("\n=== Errors ===")
        for e in out["errors"]:
            print("-", e)
    print("\n=== Answer ===")
    print(out["answer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
