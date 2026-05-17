"""Sync GraphRAG parquet data into Neo4j for llm_pipeline."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pandas as pd

from core.connection_pool import get_neo4j_driver

ID = "id"
SHORT_ID = "human_readable_id"
TITLE = "title"
TYPE = "type"
DESCRIPTION = "description"
EDGE_SOURCE = "source"
EDGE_TARGET = "target"
EDGE_WEIGHT = "weight"


def _safe_index_name(name: str) -> str:
    s = "".join(c for c in (name or "") if c.isalnum() or c == "_")
    return s or "graphEntityFulltext"


def _normalize_bolt_uri(uri: str) -> str:
    try:
        p = urlparse((uri or "").strip())
        if not p.scheme or not p.hostname:
            return uri
        if p.hostname.lower() == "localhost":
            port = p.port or 7687
            return urlunparse((p.scheme, f"127.0.0.1:{port}", p.path or "", "", "", ""))
    except Exception:
        pass
    return uri


def _wait_neo4j_ready(driver, timeout_s: float, interval_s: float = 2.0) -> None:
    if timeout_s <= 0:
        return
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            driver.verify_connectivity()
            return
        except Exception as exc:
            last_error = exc
        time.sleep(interval_s)
    msg = f"Neo4j is not ready after {timeout_s:.0f}s."
    if last_error:
        raise RuntimeError(f"{msg} Last error: {last_error}") from last_error
    raise RuntimeError(msg)


def _load_neo4j_settings(repo_root: Path) -> dict:
    cfg_path = repo_root / "config" / "neo4j.json"
    if cfg_path.is_file():
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    return {}


def _row_entity_key(row: pd.Series) -> tuple[str | None, str | None]:
    tid = row.get(SHORT_ID)
    if tid is None or (isinstance(tid, float) and pd.isna(tid)):
        tid = row.get(ID)
    if tid is None:
        return None, None
    nid = str(int(tid)) if isinstance(tid, (int, float)) and not isinstance(tid, bool) else str(tid).strip()
    raw_uuid = row.get(ID)
    uuid_s = ""
    if raw_uuid is not None and not (isinstance(raw_uuid, float) and pd.isna(raw_uuid)):
        uuid_s = str(raw_uuid).strip()
    return (nid or None), (uuid_s or None)


def _resolve_default_output_dir(repo_root: Path) -> Path | None:
    for name in ("update_output", "output"):
        d = repo_root / "graphrag" / name
        if (d / "entities.parquet").is_file():
            return d
    return None


def sync_parquet_to_neo4j(
    output_dir: Path | None = None,
    *,
    clear_existing: bool = False,
    neo4j_wait_s: float = 120.0,
) -> dict[str, int]:
    """Sync parquet files (entities/relationships/communities) into Neo4j."""
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = output_dir or _resolve_default_output_dir(repo_root)
    if out_dir is None:
        raise FileNotFoundError(
            "Cannot find entities.parquet in graphrag/update_output or graphrag/output."
        )

    entities_path = out_dir / "entities.parquet"
    rels_path = out_dir / "relationships.parquet"
    communities_path = out_dir / "communities.parquet"
    reports_path = out_dir / "community_reports.parquet"

    if not entities_path.is_file():
        raise FileNotFoundError(f"Missing file: {entities_path}")
    if not rels_path.is_file():
        raise FileNotFoundError(f"Missing file: {rels_path}")

    cfg = _load_neo4j_settings(repo_root)
    uri = _normalize_bolt_uri(os.getenv("NEO4J_URI") or cfg.get("uri") or "bolt://127.0.0.1:7687")
    user = os.getenv("NEO4J_USER") or cfg.get("user") or "neo4j"
    password = os.getenv("NEO4J_PASSWORD") or cfg.get("password")
    database = os.getenv("NEO4J_DATABASE") or cfg.get("database") or "neo4j"
    idx_entity = _safe_index_name(str(cfg.get("fulltext_index_name") or "graphEntityFulltext"))
    idx_comm = _safe_index_name(str(cfg.get("community_fulltext_index_name") or "communityFulltext"))

    if password is None:
        raise ValueError("Missing Neo4j password (config/neo4j.json or NEO4J_PASSWORD).")

    entities = pd.read_parquet(entities_path)
    rels = pd.read_parquet(rels_path)

    node_keys: set[str] = set()
    uuid_to_nid: dict[str, str] = {}
    title_to_key: dict[str, str] = {}

    driver = get_neo4j_driver(uri, user, password)
    if driver is None:
        raise RuntimeError("Cannot initialize Neo4j driver.")
    _wait_neo4j_ready(driver, neo4j_wait_s)

    inserted_entities = 0
    inserted_relationships = 0
    inserted_communities = 0
    inserted_in_community = 0

    with driver.session(database=database) as session:
        if clear_existing:
            session.run("MATCH (c:Community) DETACH DELETE c")
            session.run("MATCH (n:GraphEntity) DETACH DELETE n")

        entity_rows = []
        for _, row in entities.iterrows():
            nid, uuid_s = _row_entity_key(row)
            if not nid:
                continue
            title = str(row.get(TITLE, "") or "")
            typ = str(row.get(TYPE, "") or "")
            desc = str(row.get(DESCRIPTION, "") or "")[:8000]
            entity_rows.append(
                {
                    "id": nid,
                    "graphrag_uuid": uuid_s or "",
                    "title": title,
                    "type": typ,
                    "description": desc,
                }
            )
            node_keys.add(nid)
            if uuid_s:
                uuid_to_nid[uuid_s] = nid
            if title:
                title_to_key[title.strip().lower()] = nid

        for i in range(0, len(entity_rows), 500):
            chunk = entity_rows[i : i + 500]
            session.run(
                "UNWIND $rows AS row "
                "MERGE (n:GraphEntity {id: row.id}) "
                "SET n.graphrag_uuid = row.graphrag_uuid, n.title = row.title, "
                "n.type = row.type, n.description = row.description",
                {"rows": chunk},
            )
        inserted_entities = len(entity_rows)

        session.run(
            "CREATE CONSTRAINT graph_entity_id_unique IF NOT EXISTS "
            "FOR (n:GraphEntity) REQUIRE n.id IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT community_id_unique IF NOT EXISTS "
            "FOR (c:Community) REQUIRE c.community_id IS UNIQUE"
        )

        def resolve(endpoint: str) -> str | None:
            s = str(endpoint).strip()
            if not s:
                return None
            if s in node_keys:
                return s
            if s in uuid_to_nid:
                return uuid_to_nid[s]
            low = s.lower()
            if low in title_to_key:
                return title_to_key[low]
            for k in node_keys:
                if k.lower() == low:
                    return k
            return None

        rel_rows = []
        for _, row in rels.iterrows():
            src = row.get(EDGE_SOURCE)
            tgt = row.get(EDGE_TARGET)
            if src is None or tgt is None or (isinstance(src, float) and pd.isna(src)):
                continue
            sid = resolve(str(src).strip())
            tid = resolve(str(tgt).strip())
            if sid is None or tid is None:
                continue
            w = row.get(EDGE_WEIGHT)
            try:
                wv = float(w) if w is not None and not (isinstance(w, float) and pd.isna(w)) else 1.0
            except (TypeError, ValueError):
                wv = 1.0
            rel_rows.append({"a": sid, "b": tid, "w": wv})

        for i in range(0, len(rel_rows), 500):
            chunk = rel_rows[i : i + 500]
            session.run(
                "UNWIND $rows AS row "
                "MATCH (a:GraphEntity {id: row.a}), (b:GraphEntity {id: row.b}) "
                "MERGE (a)-[r:RELATED]->(b) SET r.weight = row.w",
                {"rows": chunk},
            )
        inserted_relationships = len(rel_rows)

        reports_by_comm: dict[int, dict[str, str | int | float]] = {}
        if reports_path.is_file():
            rep = pd.read_parquet(reports_path)
            for _, rrow in rep.iterrows():
                try:
                    cid = int(rrow["community"])
                except (TypeError, ValueError):
                    continue
                reports_by_comm[cid] = {
                    "title": str(rrow.get("title") or ""),
                    "summary": str(rrow.get("summary") or ""),
                    "level": int(rrow.get("level") or 0),
                    "rank": float(rrow.get("rank") or 0.0),
                    "full_content": str(rrow.get("full_content") or "")[:6000],
                }

        comm_rows: list[dict[str, object]] = []
        if communities_path.is_file():
            com = pd.read_parquet(communities_path)
            for _, crow in com.iterrows():
                try:
                    cid = int(crow["community"])
                except (TypeError, ValueError):
                    continue
                level = int(crow.get("level") or 0)
                title_c = str(crow.get("title") or "")
                extra = reports_by_comm.get(cid, {})
                comm_rows.append(
                    {
                        "community_id": cid,
                        "level": level,
                        "title": str(extra.get("title") or "") or title_c,
                        "summary": str(extra.get("summary") or ""),
                        "rank": float(extra.get("rank") or 0.0),
                        "full_content": str(extra.get("full_content") or "")[:6000],
                        "size": int(crow.get("size") or 0),
                    }
                )
        elif reports_by_comm:
            for cid, extra in reports_by_comm.items():
                comm_rows.append(
                    {
                        "community_id": cid,
                        "level": int(extra.get("level") or 0),
                        "title": str(extra.get("title") or ""),
                        "summary": str(extra.get("summary") or ""),
                        "rank": float(extra.get("rank") or 0.0),
                        "full_content": str(extra.get("full_content") or "")[:6000],
                        "size": 0,
                    }
                )

        if comm_rows:
            for i in range(0, len(comm_rows), 300):
                chunk = comm_rows[i : i + 300]
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (c:Community {community_id: row.community_id}) "
                    "SET c.level = row.level, c.title = row.title, c.summary = row.summary, "
                    "c.rank = row.rank, c.full_content = row.full_content, c.size = row.size",
                    {"rows": chunk},
                )
            inserted_communities = len(comm_rows)

        ic_pairs: list[dict[str, int | str]] = []
        if communities_path.is_file() and comm_rows:
            com = pd.read_parquet(communities_path)
            for _, crow in com.iterrows():
                try:
                    cid = int(crow["community"])
                except (TypeError, ValueError):
                    continue
                raw_ids = crow.get("entity_ids")
                if raw_ids is None or (isinstance(raw_ids, float) and pd.isna(raw_ids)):
                    continue
                if hasattr(raw_ids, "tolist"):
                    eids = raw_ids.tolist()
                else:
                    eids = list(raw_ids) if isinstance(raw_ids, (list, tuple)) else []
                for eid in eids:
                    eid_s = str(eid).strip()
                    nid = uuid_to_nid.get(eid_s) or (eid_s if eid_s in node_keys else resolve(eid_s))
                    if not nid:
                        continue
                    ic_pairs.append({"nid": nid, "cid": cid})
            for i in range(0, len(ic_pairs), 800):
                chunk = ic_pairs[i : i + 800]
                session.run(
                    "UNWIND $rows AS row "
                    "MATCH (e:GraphEntity {id: row.nid}), (c:Community {community_id: row.cid}) "
                    "MERGE (e)-[:IN_COMMUNITY]->(c)",
                    {"rows": chunk},
                )
            inserted_in_community = len(ic_pairs)

        session.run(
            f"CREATE FULLTEXT INDEX `{idx_entity}` IF NOT EXISTS "
            "FOR (n:GraphEntity) ON EACH [n.title, n.description]"
        )
        if comm_rows:
            session.run(
                f"CREATE FULLTEXT INDEX `{idx_comm}` IF NOT EXISTS "
                "FOR (c:Community) ON EACH [c.title, c.summary]"
            )

    return {
        "entities": inserted_entities,
        "relationships": inserted_relationships,
        "communities": inserted_communities,
        "in_community": inserted_in_community,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync GraphRAG parquet data to Neo4j from llm_pipeline.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Folder containing entities.parquet.")
    parser.add_argument("--clear", action="store_true", help="Delete existing GraphEntity/Community data first.")
    parser.add_argument(
        "--neo4j-wait",
        type=float,
        default=120.0,
        metavar="SEC",
        help="Wait for Neo4j Bolt readiness in seconds (0 to skip).",
    )
    args = parser.parse_args()

    stats = sync_parquet_to_neo4j(
        output_dir=args.output_dir,
        clear_existing=args.clear,
        neo4j_wait_s=args.neo4j_wait,
    )
    print(
        "Sync done:",
        f"entities={stats['entities']},",
        f"relationships={stats['relationships']},",
        f"communities={stats['communities']},",
        f"in_community={stats['in_community']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
