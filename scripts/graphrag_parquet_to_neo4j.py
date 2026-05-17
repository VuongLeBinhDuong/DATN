#!/usr/bin/env python3
"""
Import Microsoft GraphRAG parquet vào Neo4j:

- entities.parquet, relationships.parquet → :GraphEntity, :RELATED
- communities.parquet + community_reports.parquet → :Community, (:GraphEntity)-[:IN_COMMUNITY]->(:Community)

Entity khóa `id` (human_readable_id) + `graphrag_uuid` (cột id UUID) để nối đúng entity_ids trong communities.

Chạy sau: python -m graphrag index -r graphrag ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    import pandas as pd
    from neo4j import GraphDatabase
except ImportError as exc:
    raise SystemExit("Cần: pip install pandas pyarrow neo4j") from exc

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
    """bolt://localhost thường resolve [::1] trên Windows và gây handshake lỗi — dùng 127.0.0.1."""
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
    last: BaseException | None = None
    while time.time() < deadline:
        try:
            driver.verify_connectivity()
            return
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(interval_s)
    msg = f"Neo4j không sẵn sàng sau {timeout_s:.0f}s (Bolt)."
    if last:
        raise RuntimeError(f"{msg} Lỗi cuối: {last}") from last
    raise RuntimeError(msg)


def _load_neo4j_settings(repo: Path) -> dict:
    p = repo / "config" / "neo4j.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _row_entity_key(row: pd.Series) -> tuple[str | None, str | None]:
    """(id dùng MERGE — human_readable, uuid GraphRAG)."""
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


def _find_default_output_dir() -> Path | None:
    # Ưu tiên backup GraphRAG cũ (snapshot mới nhất) trước output hiện tại.
    backups_root = REPO_ROOT / "backups"
    if backups_root.is_dir():
        candidates = sorted(
            (p for p in backups_root.glob("*/graphrag_output") if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for d in candidates:
            if (d / "entities.parquet").is_file():
                return d

    for name in ("update_output", "output"):
        d = REPO_ROOT / "graphrag" / name
        if (d / "entities.parquet").is_file():
            return d
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Import GraphRAG parquet vào Neo4j (entity + community).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Thư mục có entities.parquet",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Xóa :GraphEntity, :Community và quan hệ liên quan trước khi import.",
    )
    parser.add_argument(
        "--neo4j-wait",
        type=float,
        default=120.0,
        metavar="SEC",
        help="Chờ Neo4j Bolt (sau docker up). 0 = không chờ. Mặc định 120.",
    )
    args = parser.parse_args()

    out_dir = args.output_dir
    if out_dir is None:
        out_dir = _find_default_output_dir()
        if out_dir is None:
            print(
                "Không tìm thấy entities.parquet trong backups/*/graphrag_output, "
                "graphrag/update_output hoặc graphrag/output.",
                file=sys.stderr,
            )
            return 1

    entities_path = out_dir / "entities.parquet"
    rels_path = out_dir / "relationships.parquet"
    communities_path = out_dir / "communities.parquet"
    reports_path = out_dir / "community_reports.parquet"

    if not entities_path.is_file():
        print(f"Thiếu file: {entities_path}", file=sys.stderr)
        return 1
    if not rels_path.is_file():
        print(f"Thiếu file: {rels_path}", file=sys.stderr)
        return 1

    cfg = _load_neo4j_settings(REPO_ROOT)
    uri = _normalize_bolt_uri(
        os.getenv("NEO4J_URI") or cfg.get("uri") or "bolt://127.0.0.1:7687"
    )
    user = os.getenv("NEO4J_USER") or cfg.get("user") or "neo4j"
    password = os.getenv("NEO4J_PASSWORD") or cfg.get("password")
    database = os.getenv("NEO4J_DATABASE") or cfg.get("database") or "neo4j"
    idx_entity = _safe_index_name(str(cfg.get("fulltext_index_name") or "graphEntityFulltext"))
    idx_comm = _safe_index_name(str(cfg.get("community_fulltext_index_name") or "communityFulltext"))

    if password is None:
        print("Thiếu password Neo4j (config/neo4j.json hoặc NEO4J_PASSWORD).", file=sys.stderr)
        return 1

    entities = pd.read_parquet(entities_path)
    rels = pd.read_parquet(rels_path)

    node_keys: set[str] = set()
    uuid_to_nid: dict[str, str] = {}
    title_to_key: dict[str, str] = {}

    print(f"Kết nối Neo4j: {uri} (database={database})")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        _wait_neo4j_ready(driver, args.neo4j_wait)
        with driver.session(database=database) as session:
            if args.clear:
                session.run("MATCH (c:Community) DETACH DELETE c")
                session.run("MATCH (n:GraphEntity) DETACH DELETE n")
                print("Đã xóa Community và GraphEntity cũ.")

            batch = []
            for _, row in entities.iterrows():
                nid, uuid_s = _row_entity_key(row)
                if not nid:
                    continue
                title = str(row.get(TITLE, "") or "")
                typ = str(row.get(TYPE, "") or "")
                desc = str(row.get(DESCRIPTION, "") or "")[:8000]
                batch.append(
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

            for i in range(0, len(batch), 500):
                chunk = batch[i : i + 500]
                session.run(
                    "UNWIND $rows AS row "
                    "MERGE (n:GraphEntity {id: row.id}) "
                    "SET n.graphrag_uuid = row.graphrag_uuid, "
                    "n.title = row.title, n.type = row.type, n.description = row.description",
                    {"rows": chunk},
                )
            print(f"Đã MERGE {len(batch)} nút GraphEntity (kèm graphrag_uuid khi có).")

            try:
                session.run(
                    "CREATE CONSTRAINT graph_entity_id_unique IF NOT EXISTS "
                    "FOR (n:GraphEntity) REQUIRE n.id IS UNIQUE"
                )
                session.run(
                    "CREATE CONSTRAINT community_id_unique IF NOT EXISTS "
                    "FOR (c:Community) REQUIRE c.community_id IS UNIQUE"
                )
                print("Đã đảm bảo constraint UNIQUE cho GraphEntity.id và Community.community_id.")
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] Constraint: {exc}")

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
            skipped = 0
            for _, row in rels.iterrows():
                src = row.get(EDGE_SOURCE)
                tgt = row.get(EDGE_TARGET)
                if src is None or tgt is None or (isinstance(src, float) and pd.isna(src)):
                    skipped += 1
                    continue
                sid = resolve(str(src).strip())
                tid = resolve(str(tgt).strip())
                if sid is None or tid is None:
                    skipped += 1
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
            print(f"Đã MERGE {len(rel_rows)} cạnh RELATED (bỏ qua {skipped}).")

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
                    summary = str(extra.get("summary") or "")
                    title_r = str(extra.get("title") or "")
                    rank = float(extra.get("rank") or 0.0)
                    fc = str(extra.get("full_content") or "")[:6000]
                    comm_rows.append(
                        {
                            "community_id": cid,
                            "level": level,
                            "title": title_r or title_c,
                            "summary": summary,
                            "rank": rank,
                            "full_content": fc,
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
                print(f"Đã MERGE {len(comm_rows)} nút Community (từ communities/community_reports).")
            else:
                print("[WARN] Không có communities.parquet / community_reports — bỏ qua Community.")

            in_comm = 0
            skipped_ic = 0
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
                        nid = None
                        if eid_s in uuid_to_nid:
                            nid = uuid_to_nid[eid_s]
                        elif eid_s in node_keys:
                            nid = eid_s
                        else:
                            nid = resolve(eid_s)
                        if not nid:
                            skipped_ic += 1
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
                    in_comm += len(chunk)
                print(f"Đã MERGE {in_comm} cạnh IN_COMMUNITY (bỏ qua khớp entity {skipped_ic}).")

            session.run(
                f"CREATE FULLTEXT INDEX `{idx_entity}` IF NOT EXISTS "
                "FOR (n:GraphEntity) ON EACH [n.title, n.description]"
            )
            if comm_rows:
                session.run(
                    f"CREATE FULLTEXT INDEX `{idx_comm}` IF NOT EXISTS "
                    "FOR (c:Community) ON EACH [c.title, c.summary]"
                )
            print(f"Đã đảm bảo fulltext index `{idx_entity}`" + (f", `{idx_comm}`." if comm_rows else "."))

    finally:
        driver.close()

    print("Xong. Bật Neo4j query: config/neo4j.json — enabled=true, query_backend=neo4j.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
