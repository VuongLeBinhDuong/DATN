#!/usr/bin/env python3
"""
Export Microsoft GraphRAG parquet tables to GraphML for visualization (Gephi, yEd, etc.).

Reads:
  <output-dir>/entities.parquet
  <output-dir>/relationships.parquet

(standard GraphRAG index output layout under output_storage.base_dir)
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install pandas: pip install pandas pyarrow") from exc

# GraphRAG schema field names (graphrag.data_model.schemas)
ID = "id"
SHORT_ID = "human_readable_id"
TITLE = "title"
TYPE = "type"
DESCRIPTION = "description"
EDGE_SOURCE = "source"
EDGE_TARGET = "target"
EDGE_WEIGHT = "weight"


def _xml_escape(s: str) -> str:
    if not s:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def export_graphml(
    entities_path: Path,
    relationships_path: Path,
    out_path: Path,
) -> tuple[int, int, int, int]:
    """Return (nodes_written, edges_written, skipped_edges, dropped_empty_nodes)."""
    if not entities_path.is_file():
        raise FileNotFoundError(f"Missing entities file: {entities_path}")
    if not relationships_path.is_file():
        raise FileNotFoundError(f"Missing relationships file: {relationships_path}")

    entities = pd.read_parquet(entities_path)
    rels = pd.read_parquet(relationships_path)

    ns = "http://graphml.graphdrawing.org/xmlns"
    ET.register_namespace("", ns)

    graphml = ET.Element(f"{{{ns}}}graphml")
    for key_id, attr_name, attr_type in (
        ("d0", "title", "string"),
        ("d1", "type", "string"),
        ("d2", "description", "string"),
    ):
        ET.SubElement(
            graphml,
            f"{{{ns}}}key",
            {
                "id": key_id,
                "for": "node",
                "attr.name": attr_name,
                "attr.type": attr_type,
            },
        )
    ET.SubElement(
        graphml,
        f"{{{ns}}}key",
        {
            "id": "d3",
            "for": "edge",
            "attr.name": "weight",
            "attr.type": "double",
        },
    )

    graph = ET.SubElement(graphml, f"{{{ns}}}graph", id="G", edgedefault="undirected")

    # node_id -> display label for matching edges (often source/target are titles)
    node_keys: set[str] = set()
    title_to_key: dict[str, str] = {}
    dropped_empty = 0

    for _, row in entities.iterrows():
        tid = row.get(SHORT_ID, row.get(ID))
        if tid is None or (isinstance(tid, float) and pd.isna(tid)):
            tid = row.get(ID)
        if tid is None:
            dropped_empty += 1
            continue
        nid = str(int(tid)) if isinstance(tid, (int, float)) and not isinstance(tid, bool) else str(tid).strip()
        if not nid:
            dropped_empty += 1
            continue
        title = str(row.get(TITLE, "") or "")
        typ = str(row.get(TYPE, "") or "")
        desc = str(row.get(DESCRIPTION, "") or "")[:4000]

        node = ET.SubElement(graph, f"{{{ns}}}node", id=_xml_escape(nid))
        data0 = ET.SubElement(node, f"{{{ns}}}data", key="d0")
        data0.text = title
        data1 = ET.SubElement(node, f"{{{ns}}}data", key="d1")
        data1.text = typ
        data2 = ET.SubElement(node, f"{{{ns}}}data", key="d2")
        data2.text = desc

        node_keys.add(nid)
        if title:
            title_to_key[title.strip().lower()] = nid

    edges_written = 0
    skipped = 0
    eid = 0
    for _, row in rels.iterrows():
        src = row.get(EDGE_SOURCE)
        tgt = row.get(EDGE_TARGET)
        if src is None or tgt is None or (isinstance(src, float) and pd.isna(src)):
            skipped += 1
            continue
        s = str(src).strip()
        t = str(tgt).strip()
        if not s or not t:
            skipped += 1
            continue

        def resolve(endpoint: str) -> str | None:
            if endpoint in node_keys:
                return endpoint
            low = endpoint.lower()
            if low in title_to_key:
                return title_to_key[low]
            for k in node_keys:
                if k.lower() == low:
                    return k
            return None

        sid = resolve(s)
        tid = resolve(t)
        if sid is None or tid is None:
            skipped += 1
            continue

        w = row.get(EDGE_WEIGHT)
        try:
            wv = float(w) if w is not None and not (isinstance(w, float) and pd.isna(w)) else 1.0
        except (TypeError, ValueError):
            wv = 1.0

        edge = ET.SubElement(
            graph,
            f"{{{ns}}}edge",
            id=f"e{eid}",
            source=_xml_escape(sid),
            target=_xml_escape(tid),
        )
        wd = ET.SubElement(edge, f"{{{ns}}}data", key="d3")
        wd.text = str(wv)
        eid += 1
        edges_written += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(graphml)
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="utf-8", xml_declaration=True, default_namespace=ns)

    return len(node_keys), edges_written, skipped, dropped_empty


def main() -> int:
    parser = argparse.ArgumentParser(description="Export GraphRAG entities/relationships to GraphML.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "graphrag" / "output",
        help="GraphRAG output storage base_dir (contains entities.parquet)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output .graphml path (default: <output-dir>/graph.graphml)",
    )
    args = parser.parse_args()

    out_dir = args.output_dir
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    entities_path = out_dir / "entities.parquet"
    relationships_path = out_dir / "relationships.parquet"
    out_path = args.out or (out_dir / "graph.graphml")
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path

    try:
        nodes, edges, skipped, dropped = export_graphml(entities_path, relationships_path, out_path)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        print(
            "Run GraphRAG index first so entities.parquet and relationships.parquet exist under output-dir.",
            file=sys.stderr,
        )
        return 1

    print(f"Wrote graphml: {out_path}")
    print(f"nodes={nodes}, edges={edges}, skipped_edges={skipped}, dropped_empty_nodes={dropped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
