#!/usr/bin/env python3
"""Chunk → embedding → ghi vào vector store (Milvus)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pymilvus import MilvusClient
from sentence_transformers import SentenceTransformer

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_rows(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"{p} must be a JSON list")
        for item in data:
            if isinstance(item, dict):
                rows.append(item)
    return rows


def row_to_doc(rec: dict) -> dict | None:
    text = str(rec.get("content") or "").strip()
    if not text:
        return None
    title = str(rec.get("title") or rec.get("question") or "")[:512]
    link = str(rec.get("source_url") or "")[:2048]
    source = str(rec.get("source_org") or "")[:256]
    return {
        "text": text[:60000],
        "title": title,
        "link": link,
        "source": source,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Index JSON rows into Milvus (dynamic schema + vector).")
    parser.add_argument("--input", nargs="+", type=Path, required=True, help="JSON list files (e.g. medical_reference_vi_qa.json)")
    parser.add_argument("--uri", default="http://localhost:19530")
    parser.add_argument("--collection", default="chunks")
    parser.add_argument(
        "--embedding-model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="SentenceTransformer model.",
    )
    parser.add_argument(
        "--insert-batch-size",
        type=int,
        default=2000,
        help="Rows per insert batch (gRPC payload size; lower if RESOURCE_EXHAUSTED).",
    )
    parser.add_argument("--no-drop", action="store_true", help="Do not drop collection if it exists")
    args = parser.parse_args()

    rows = load_rows(args.input)
    docs: list[dict] = []
    for rec in rows:
        d = row_to_doc(rec)
        if d:
            docs.append(d)
    if not docs:
        print("No documents to index.", file=sys.stderr)
        return 1

    for i, d in enumerate(docs):
        d["id"] = i

    model = SentenceTransformer(args.embedding_model)
    dim = model.get_sentence_embedding_dimension()

    client = MilvusClient(uri=args.uri)
    name = args.collection
    if not args.no_drop and client.has_collection(name):
        client.drop_collection(name)

    client.create_collection(
        collection_name=name,
        dimension=dim,
        primary_field_name="id",
        id_type="int",
        vector_field_name="vector",
        metric_type="COSINE",
        auto_id=False,
    )

    batch = max(1, args.insert_batch_size)
    for start in range(0, len(docs), batch):
        chunk = docs[start : start + batch]
        texts = [c["text"] for c in chunk]
        vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
        payload: list[dict] = []
        for c, v in zip(chunk, vecs, strict=True):
            payload.append(
                {
                    "id": c["id"],
                    "vector": v.tolist(),
                    "text": c["text"],
                    "title": c["title"],
                    "link": c["link"],
                    "source": c["source"],
                }
            )
        client.insert(collection_name=name, data=payload)

    cfg_out = REPO_ROOT / "config" / "store.json"
    cfg_out.parent.mkdir(parents=True, exist_ok=True)
    cfg_out.write_text(
        json.dumps(
            {
                "uri": args.uri,
                "collection": name,
                "embedding_model": args.embedding_model,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Indexed {len(docs)} rows → {name}. Wrote {cfg_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
