from __future__ import annotations

import argparse
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from kg.neo4j_client import Neo4jKGClient


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply custom KG schema to Neo4j.")
    ap.add_argument(
        "--schema",
        default=str(Path("kg") / "schema.cypher"),
        help="Path to schema.cypher (default: kg/schema.cypher)",
    )
    args = ap.parse_args()

    client = Neo4jKGClient()
    n = client.apply_schema(args.schema)
    print(f"Applied {n} Cypher statements from {args.schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

