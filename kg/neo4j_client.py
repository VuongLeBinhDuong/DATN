from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from core.connection_pool import get_neo4j_driver
from core.settings import get_settings

from kg.models import (
    ChunkRecord,
    DocumentRecord,
    EntityRecord,
    MentionRecord,
    RelationRecord,
    now_iso,
)
from kg.ontology import normalize_predicate


def _split_cypher_statements(text: str) -> list[str]:
    # Minimal statement splitter: split on ';' at line ends, ignore blank/comment lines.
    buf: list[str] = []
    cur: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("//"):
            continue
        cur.append(line)
        if line.strip().endswith(";"):
            stmt = "\n".join(cur).rstrip().rstrip(";").strip()
            if stmt:
                buf.append(stmt)
            cur = []
    tail = "\n".join(cur).strip()
    if tail:
        buf.append(tail)
    return buf


class Neo4jKGClient:
    """Neo4j client for custom KG (Document/Chunk/Entity)."""

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self._cfg = cfg
        self._driver = None

    def _connection(self) -> tuple[Any, str]:
        settings = get_settings()
        neo = settings.neo4j
        uri = os.getenv("NEO4J_URI") or (self._cfg or {}).get("uri") or neo.uri
        user = os.getenv("NEO4J_USER") or (self._cfg or {}).get("user") or neo.user
        password = os.getenv("NEO4J_PASSWORD") or (self._cfg or {}).get("password") or neo.password
        database = os.getenv("NEO4J_DATABASE") or (self._cfg or {}).get("database") or neo.database or "neo4j"

        if not uri or not user or password is None:
            raise RuntimeError("Neo4j connection parameters missing (NEO4J_URI/USER/PASSWORD).")

        driver = get_neo4j_driver(str(uri), str(user), str(password))
        if driver is None:
            raise RuntimeError("Neo4j driver not available (pip install neo4j).")
        return driver, str(database)

    def apply_schema(self, schema_path: str | Path) -> int:
        """Apply Cypher schema file; returns number of statements executed.
        
        Continues on individual statement errors (useful for optional indexes).
        """
        p = Path(schema_path)
        text = p.read_text(encoding="utf-8")
        statements = _split_cypher_statements(text)
        if not statements:
            return 0

        driver, db = self._connection()
        executed = 0
        failed = []
        with driver.session(database=db) as session:
            for stmt in statements:
                try:
                    session.run(stmt).consume()
                    executed += 1
                except Exception as e:
                    # Log and continue - some statements (like fulltext) may be optional
                    failed.append((stmt[:80], str(e)[:100]))
        
        if failed:
            print(f"Warning: {len(failed)} statement(s) failed (may be optional):")
            for stmt, err in failed:
                print(f"  - {stmt}... : {err}")
        return executed

    def upsert_documents(self, docs: Iterable[DocumentRecord]) -> int:
        driver, db = self._connection()
        rows = []
        for d in docs:
            payload = asdict(d)
            payload["created_at"] = payload.get("created_at") or now_iso()
            rows.append(payload)
        if not rows:
            return 0

        cypher = (
            "UNWIND $rows AS r "
            "MERGE (d:Document {doc_id: r.doc_id}) "
            "SET d.title = coalesce(r.title, d.title), "
            "    d.source = coalesce(r.source, d.source), "
            "    d.created_at = coalesce(d.created_at, r.created_at) "
            "RETURN count(d) AS n"
        )
        with driver.session(database=db) as session:
            return int(session.run(cypher, {"rows": rows}).single()["n"])

    def upsert_chunks(self, chunks: Iterable[ChunkRecord]) -> int:
        driver, db = self._connection()
        rows = []
        for c in chunks:
            payload = asdict(c)
            payload["created_at"] = payload.get("created_at") or now_iso()
            rows.append(payload)
        if not rows:
            return 0

        cypher = (
            "UNWIND $rows AS r "
            "MERGE (c:Chunk {chunk_id: r.chunk_id}) "
            "SET c.doc_id = r.doc_id, "
            "    c.text = r.text, "
            "    c.section_path = r.section_path, "
            "    c.start_offset = r.start_offset, "
            "    c.end_offset = r.end_offset, "
            "    c.created_at = coalesce(c.created_at, r.created_at), "
            "    c.title = left(r.text, 60) + CASE WHEN size(r.text) > 60 THEN '...' ELSE '' END "
            "WITH c, r "
            "MERGE (d:Document {doc_id: r.doc_id}) "
            "ON CREATE SET d.created_at = coalesce(d.created_at, r.created_at) "
            "MERGE (d)-[:HAS_CHUNK]->(c) "
            "RETURN count(c) AS n"
        )
        with driver.session(database=db) as session:
            return int(session.run(cypher, {"rows": rows}).single()["n"])

    def upsert_entities(self, entities: Iterable[EntityRecord]) -> int:
        driver, db = self._connection()
        rows = []
        for e in entities:
            payload = asdict(e)
            payload["aliases"] = payload.get("aliases") or []
            payload["created_at"] = payload.get("created_at") or now_iso()
            rows.append(payload)
        if not rows:
            return 0

        cypher = (
            "UNWIND $rows AS r "
            "MERGE (e:Entity {entity_id: r.entity_id}) "
            "SET e.canonical_name = r.canonical_name, "
            "    e.type = coalesce(r.type, e.type), "
            "    e.aliases = coalesce(r.aliases, e.aliases), "
            "    e.created_at = coalesce(e.created_at, r.created_at) "
            "RETURN count(e) AS n"
        )
        with driver.session(database=db) as session:
            return int(session.run(cypher, {"rows": rows}).single()["n"])

    def upsert_mentions(self, mentions: Iterable[MentionRecord]) -> int:
        driver, db = self._connection()
        rows = [asdict(m) for m in mentions]
        if not rows:
            return 0

        cypher = (
            "UNWIND $rows AS r "
            "MATCH (c:Chunk {chunk_id: r.chunk_id}) "
            "MATCH (e:Entity {entity_id: r.entity_id}) "
            "MERGE (c)-[m:MENTIONS]->(e) "
            "SET m.confidence = r.confidence, "
            "    m.start_char = r.start_char, "
            "    m.end_char = r.end_char "
            "RETURN count(m) AS n"
        )
        with driver.session(database=db) as session:
            return int(session.run(cypher, {"rows": rows}).single()["n"])

    def upsert_relations(self, rels: Iterable[RelationRecord]) -> int:
        driver, db = self._connection()
        raw_rows = [asdict(r) for r in rels]
        if not raw_rows:
            return 0
        
        # Normalize predicates to canonical ontology
        rows = []
        for r in raw_rows:
            r_copy = dict(r)
            r_copy["predicate"] = normalize_predicate(r_copy.get("predicate"))
            rows.append(r_copy)

        cypher = (
            "UNWIND $rows AS r "
            "MATCH (a:Entity {entity_id: r.subject_entity_id}) "
            "MATCH (b:Entity {entity_id: r.object_entity_id}) "
            "MERGE (a)-[x:REL {predicate: r.predicate}]->(b) "
            "SET x.confidence = r.confidence, "
            "    x.evidence_chunk_id = r.evidence_chunk_id "
            "RETURN count(x) AS n"
        )
        with driver.session(database=db) as session:
            return int(session.run(cypher, {"rows": rows}).single()["n"])

    def fetch_chunks(
        self,
        *,
        limit: int = 50,
        skip: int = 0,
        doc_id: str | None = None,
    ) -> list[dict[str, Any]]:
        driver, db = self._connection()
        cypher = (
            "MATCH (c:Chunk) "
            "WHERE ($doc_id IS NULL OR c.doc_id = $doc_id) "
            "RETURN c.chunk_id AS chunk_id, c.doc_id AS doc_id, "
            "       coalesce(c.section_path,'') AS section_path, "
            "       c.text AS text "
            "ORDER BY c.chunk_id "
            "SKIP $skip LIMIT $limit"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"limit": int(limit), "skip": int(skip), "doc_id": doc_id})]

    def fetch_chunks_without_mentions(
        self,
        *,
        limit: int = 50,
        skip: int = 0,
        doc_id: str | None = None,
    ) -> list[dict[str, Any]]:
        driver, db = self._connection()
        cypher = (
            "MATCH (c:Chunk) "
            "WHERE ($doc_id IS NULL OR c.doc_id = $doc_id) "
            "AND NOT (c)-[:MENTIONS]->(:Entity) "
            "RETURN c.chunk_id AS chunk_id, c.doc_id AS doc_id, "
            "       coalesce(c.section_path,'') AS section_path, "
            "       c.text AS text "
            "ORDER BY c.chunk_id "
            "SKIP $skip LIMIT $limit"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"limit": int(limit), "skip": int(skip), "doc_id": doc_id})]

    def fetch_entities_for_chunk(self, chunk_id: str) -> list[dict[str, Any]]:
        driver, db = self._connection()
        cypher = (
            "MATCH (c:Chunk {chunk_id: $cid})-[m:MENTIONS]->(e:Entity) "
            "RETURN e.entity_id AS entity_id, e.canonical_name AS canonical_name, "
            "       coalesce(e.type,'') AS type, coalesce(e.aliases, []) AS aliases, "
            "       coalesce(m.confidence, 0.5) AS mention_confidence "
            "ORDER BY mention_confidence DESC, canonical_name ASC"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"cid": chunk_id})]

    def fetch_chunks_without_relations(
        self,
        *,
        limit: int = 50,
        skip: int = 0,
        doc_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Chunks that have mentions but no relations attributed to them (by evidence_chunk_id)."""
        driver, db = self._connection()
        cypher = (
            "MATCH (c:Chunk) "
            "WHERE ($doc_id IS NULL OR c.doc_id = $doc_id) "
            "AND (c)-[:MENTIONS]->(:Entity) "
            "AND NOT EXISTS { MATCH (:Entity)-[:REL {evidence_chunk_id: c.chunk_id}]->(:Entity) } "
            "RETURN c.chunk_id AS chunk_id, c.doc_id AS doc_id, "
            "       coalesce(c.section_path,'') AS section_path, "
            "       c.text AS text "
            "ORDER BY c.chunk_id "
            "SKIP $skip LIMIT $limit"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"limit": int(limit), "skip": int(skip), "doc_id": doc_id})]

    def search_entities_fulltext(self, query: str, *, limit: int = 12, index_name: str = "kgEntityFulltext") -> list[dict[str, Any]]:
        """Search entities by canonical_name AND aliases (synonym-aware).
        
        Supports medical synonyms: tiểu đường = đái tháo đường = diabetes
        """
        driver, db = self._connection()

        q = (query or "").strip().lower()
        if not q or q == "*":
            return []

        # Build pattern for word matching
        words = [w for w in q.split() if len(w) >= 2]
        if not words:
            words = [q]

        # Search both canonical_name AND aliases for synonym matching
        # Example: query "tiểu đường" matches entity with canonical_name "đái tháo đường" 
        # if "tiểu đường" is in aliases
        cypher = (
            "MATCH (e:Entity) "
            "WHERE " + " OR ".join([
                f"(toLower(e.canonical_name) CONTAINS $word{i} "
                f" OR ANY(alias IN coalesce(e.aliases, []) WHERE toLower(alias) CONTAINS $word{i}))"
                for i in range(len(words))
            ]) + " "
            "RETURN e.entity_id AS entity_id, e.canonical_name AS canonical_name, "
            "       coalesce(e.type,'') AS type, coalesce(e.aliases, []) AS aliases, "
            "       1.0 AS score "
            "LIMIT $lim"
        )

        params = {f"word{i}": w for i, w in enumerate(words)}
        params["lim"] = int(limit) * 3

        with driver.session(database=db) as session:
            results = [dict(r) for r in session.run(cypher, params)]
            seen = set()
            unique = []
            for r in results:
                eid = r.get("entity_id")
                if eid and eid not in seen:
                    seen.add(eid)
                    unique.append(r)
                    if len(unique) >= limit:
                        break
            return unique

    def search_entities_native_fulltext(
        self, query: str, *, limit: int = 12, index_name: str = "kgEntityFulltext"
    ) -> list[dict[str, Any]] | None:
        """Try native Neo4j fulltext index. Returns None if index doesn't exist."""
        driver, db = self._connection()
        q = (query or "").strip()
        if not q or q == "*":
            return []
        
        # Escape special characters for fulltext query
        escaped = q.replace('"', '\\"').replace("'", "\\'")
        
        cypher = (
            f"CALL db.index.fulltext.queryNodes($index, $query) "
            "YIELD node, score "
            "RETURN node.entity_id AS entity_id, node.canonical_name AS canonical_name, "
            "       coalesce(node.type,'') AS type, coalesce(node.aliases, []) AS aliases, "
            "       score "
            "LIMIT $lim"
        )
        
        try:
            with driver.session(database=db) as session:
                results = [
                    dict(r) 
                    for r in session.run(cypher, {"index": index_name, "query": escaped, "lim": int(limit)})
                ]
                return results
        except Exception:
            # Index doesn't exist or query failed
            return None

    def expand_subgraph(
        self,
        seed_entity_ids: list[str],
        *,
        hops: int = 2,
        max_edges: int = 200,
    ) -> dict[str, Any]:
        """Return subgraph around seed entities (entities + REL edges)."""
        driver, db = self._connection()
        hops = max(0, min(int(hops), 3))
        if not seed_entity_ids:
            return {"entities": [], "edges": []}

        # Get entities within k hops (undirected), then fetch directed REL edges among them.
        # Note: Neo4j doesn't allow parameters in relationship patterns like [:REL*0..$h]
        # So we format the hops directly into the query string.
        cypher_nodes = (
            f"MATCH (s:Entity) WHERE s.entity_id IN $seed "
            f"CALL (s) {{ "
            f"  MATCH p=(s)-[:REL*0..{hops}]-(:Entity) "
            f"  UNWIND nodes(p) AS n "
            f"  RETURN DISTINCT n.entity_id AS entity_id "
            f"}} "
            f"RETURN DISTINCT entity_id"
        )
        with driver.session(database=db) as session:
            ids = [r["entity_id"] for r in session.run(cypher_nodes, {"seed": seed_entity_ids})]
            if not ids:
                ids = list(seed_entity_ids)

            cypher_entities = (
                "MATCH (e:Entity) WHERE e.entity_id IN $ids "
                "RETURN e.entity_id AS entity_id, e.canonical_name AS canonical_name, "
                "       coalesce(e.type,'') AS type, coalesce(e.aliases, []) AS aliases"
            )
            entities = [dict(r) for r in session.run(cypher_entities, {"ids": ids})]

            cypher_edges = (
                "MATCH (a:Entity)-[r:REL]->(b:Entity) "
                "WHERE a.entity_id IN $ids AND b.entity_id IN $ids "
                "RETURN a.entity_id AS subject_entity_id, b.entity_id AS object_entity_id, "
                "       r.predicate AS predicate, coalesce(r.confidence,0.5) AS confidence, "
                "       r.evidence_chunk_id AS evidence_chunk_id "
                "ORDER BY confidence DESC "
                "LIMIT $lim"
            )
            edges = [dict(r) for r in session.run(cypher_edges, {"ids": ids, "lim": int(max_edges)})]

        return {"entities": entities, "edges": edges}

    def fetch_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []
        driver, db = self._connection()
        cypher = (
            "MATCH (c:Chunk) WHERE c.chunk_id IN $ids "
            "RETURN c.chunk_id AS chunk_id, c.doc_id AS doc_id, "
            "       coalesce(c.section_path,'') AS section_path, c.text AS text"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"ids": chunk_ids})]

    def fetch_chunks_mentioning_entities(
        self,
        entity_ids: list[str],
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if not entity_ids:
            return []
        driver, db = self._connection()
        cypher = (
            "MATCH (c:Chunk)-[m:MENTIONS]->(e:Entity) "
            "WHERE e.entity_id IN $eids "
            "WITH c, max(coalesce(m.confidence,0.5)) AS mc "
            "RETURN c.chunk_id AS chunk_id, c.doc_id AS doc_id, "
            "       coalesce(c.section_path,'') AS section_path, c.text AS text, mc AS mention_confidence "
            "ORDER BY mention_confidence DESC "
            "LIMIT $lim"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"eids": entity_ids, "lim": int(limit)})]

    # --------------------
    # Artifact export/import helpers (JSONL)
    # --------------------

    def clear_custom_kg(self) -> dict[str, int]:
        """Delete custom KG nodes/edges (Document/Chunk/Entity). Safe to rerun."""
        driver, db = self._connection()
        stats: dict[str, int] = {}
        with driver.session(database=db) as session:
            # Delete relationships first (optional), then nodes.
            res1 = session.run("MATCH ()-[r:REL]->() DELETE r RETURN count(r) AS n").single()
            res2 = session.run("MATCH ()-[m:MENTIONS]->() DELETE m RETURN count(m) AS n").single()
            res3 = session.run("MATCH ()-[h:HAS_CHUNK]->() DELETE h RETURN count(h) AS n").single()
            res4 = session.run("MATCH (c:Chunk) DETACH DELETE c RETURN count(c) AS n").single()
            res5 = session.run("MATCH (e:Entity) DETACH DELETE e RETURN count(e) AS n").single()
            res6 = session.run("MATCH (d:Document) DETACH DELETE d RETURN count(d) AS n").single()
            stats["rel_edges_deleted"] = int(res1["n"])
            stats["mentions_deleted"] = int(res2["n"])
            stats["has_chunk_deleted"] = int(res3["n"])
            stats["chunks_deleted"] = int(res4["n"])
            stats["entities_deleted"] = int(res5["n"])
            stats["documents_deleted"] = int(res6["n"])
        return stats

    def export_documents(self, *, limit: int = 1000, skip: int = 0) -> list[dict[str, Any]]:
        driver, db = self._connection()
        cypher = (
            "MATCH (d:Document) "
            "RETURN d.doc_id AS doc_id, d.title AS title, d.source AS source, d.created_at AS created_at "
            "ORDER BY d.doc_id "
            "SKIP $skip LIMIT $limit"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"skip": int(skip), "limit": int(limit)})]

    def export_chunks(self, *, limit: int = 1000, skip: int = 0) -> list[dict[str, Any]]:
        driver, db = self._connection()
        cypher = (
            "MATCH (c:Chunk) "
            "RETURN c.chunk_id AS chunk_id, c.doc_id AS doc_id, c.text AS text, "
            "       c.section_path AS section_path, c.start_offset AS start_offset, "
            "       c.end_offset AS end_offset, c.created_at AS created_at "
            "ORDER BY c.chunk_id "
            "SKIP $skip LIMIT $limit"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"skip": int(skip), "limit": int(limit)})]

    def export_entities(self, *, limit: int = 1000, skip: int = 0) -> list[dict[str, Any]]:
        driver, db = self._connection()
        cypher = (
            "MATCH (e:Entity) "
            "RETURN e.entity_id AS entity_id, e.canonical_name AS canonical_name, "
            "       e.type AS type, coalesce(e.aliases, []) AS aliases, e.created_at AS created_at "
            "ORDER BY e.entity_id "
            "SKIP $skip LIMIT $limit"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"skip": int(skip), "limit": int(limit)})]

    def export_mentions(self, *, limit: int = 2000, skip: int = 0) -> list[dict[str, Any]]:
        driver, db = self._connection()
        cypher = (
            "MATCH (c:Chunk)-[m:MENTIONS]->(e:Entity) "
            "RETURN c.chunk_id AS chunk_id, e.entity_id AS entity_id, "
            "       coalesce(m.confidence, 0.5) AS confidence, m.start_char AS start_char, m.end_char AS end_char "
            "ORDER BY c.chunk_id, e.entity_id "
            "SKIP $skip LIMIT $limit"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"skip": int(skip), "limit": int(limit)})]

    def export_relations(self, *, limit: int = 2000, skip: int = 0) -> list[dict[str, Any]]:
        driver, db = self._connection()
        cypher = (
            "MATCH (a:Entity)-[r:REL]->(b:Entity) "
            "RETURN a.entity_id AS subject_entity_id, b.entity_id AS object_entity_id, "
            "       r.predicate AS predicate, coalesce(r.confidence,0.5) AS confidence, "
            "       r.evidence_chunk_id AS evidence_chunk_id "
            "ORDER BY a.entity_id, b.entity_id, r.predicate "
            "SKIP $skip LIMIT $limit"
        )
        with driver.session(database=db) as session:
            return [dict(r) for r in session.run(cypher, {"skip": int(skip), "limit": int(limit)})]

    def find_paths_between_entities(
        self,
        entity_ids: list[str],
        *,
        max_hops: int = 2,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Find direct paths (length 1 to max_hops) linking the specified seed entity IDs in the graph.
        
        Returns a subgraph dict: {"entities": [...], "edges": [...]} containing the path nodes and edges.
        """
        driver, db = self._connection()
        max_hops = max(1, min(int(max_hops), 3))
        if len(entity_ids) < 2:
            return {"entities": [], "edges": []}
            
        cypher = (
            f"MATCH p=(a:Entity)-[:REL*1..{max_hops}]-(b:Entity) "
            f"WHERE a.entity_id IN $ids AND b.entity_id IN $ids AND a.entity_id < b.entity_id "
            f"WITH p LIMIT $lim "
            f"UNWIND nodes(p) AS n "
            f"UNWIND relationships(p) AS r "
            f"WITH collect(distinct n) AS ns, collect(distinct r) AS rs "
            f"RETURN [e IN ns | {{entity_id: e.entity_id, canonical_name: e.canonical_name, type: coalesce(e.type, ''), aliases: coalesce(e.aliases, [])}}] AS entities, "
            f"       [x IN rs | {{subject_entity_id: startNode(x).entity_id, object_entity_id: endNode(x).entity_id, "
            f"                    predicate: x.predicate, confidence: coalesce(x.confidence, 0.5), "
            f"                    evidence_chunk_id: x.evidence_chunk_id}}] AS edges"
        )
        with driver.session(database=db) as session:
            res = session.run(cypher, {"ids": entity_ids, "lim": int(limit)}).single()
            if res:
                return {
                    "entities": res["entities"] or [],
                    "edges": res["edges"] or []
                }
        return {"entities": [], "edges": []}


