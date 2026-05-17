#!/usr/bin/env python3
"""
Tai anh tim kiem bang icrawler — KHONG can API key, KHONG ton tien.

  * Crawl trang web Bing Images (giong khi mo trinh duyet), khong dung Azure API.

Mac dinh: Bing Images (on dinh hon). Google Images thuong tra ve trang chi co JS
(consent/challenge) — parser icrawler khong doc duoc -> loi NoneType.

Sau khi tai: moi thu muc thuoc (vd paracetamol/) co labels.jsonl — drug, query, filename, source_url, width, height.

Nhieu thuoc, moi thuoc 1-2 anh:
  python scripts/crawl_pill_images_icrawler.py --drugs-file scripts/drugs_many.txt --per-drug 2 --sleep-between-drugs 0.5

Chay:
  python scripts/crawl_pill_images_icrawler.py --drugs-file scripts/drugs_many.txt --max-num 50
  python scripts/crawl_pill_images_icrawler.py --engine google --drug paracetamol --max-num 30   # thuong that bai

Luu y phap ly: chi nghien cuu/DATN; tuan thu ToS khi phan phoi du lieu.
"""

from __future__ import annotations

import argparse
import csv
import html as html_module
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from icrawler.builtin import BingImageCrawler, GoogleImageCrawler
from icrawler.downloader import ImageDownloader
from icrawler.builtin.bing import BingParser
from icrawler.builtin.google import GoogleParser


class RobustGoogleParser(GoogleParser):
    """Trich 'ou' trong JSON neu co; tranh tra ve None (icrawler can iterable)."""

    def parse(self, response):
        text = response.content.decode("utf-8", "ignore")
        seen: set[str] = set()
        for m in re.finditer(r'"ou"\s*:\s*"([^"]+)"', text):
            url = m.group(1).replace("\\/", "/")
            if url.startswith("http") and url not in seen:
                seen.add(url)
                yield {"file_url": url}
        if seen:
            return
        legacy = GoogleParser.parse(self, response)
        if legacy:
            yield from legacy


class RobustBingParser(BingParser):
    """Them anh .png/.webp (parser goc chi khop .jpg trong murl)."""

    def parse(self, response):
        text = response.content.decode("utf-8", "ignore")
        seen: set[str] = set()
        for m in re.finditer(r'"murl"\s*:\s*"([^"]+)"', text):
            raw = m.group(1).replace("\\/", "/")
            url = html_module.unescape(raw)
            if url.startswith("http") and url not in seen:
                seen.add(url)
                yield {"file_url": url}
        if seen:
            return
        yield from BingParser.parse(self, response)


def _make_labeled_image_downloader(
    *,
    drug: str,
    query: str,
    engine: str,
    sub_slug: str,
    labels_path: Path,
    write_lock: threading.Lock,
) -> type[ImageDownloader]:
    """Factory: downloader ghi labels.jsonl (ten thuoc + URL + file local)."""

    class LabeledImageDownloader(ImageDownloader):
        def process_meta(self, task: dict[str, Any]) -> None:
            if not task.get("success") or not task.get("filename"):
                return
            sz = task.get("img_size")
            w, h = (int(sz[0]), int(sz[1])) if sz else (None, None)
            rec = {
                "drug": drug,
                "query": query,
                "engine": engine,
                "filename": task["filename"],
                "relative_path": f"{sub_slug}/{task['filename']}".replace("\\", "/"),
                "source_url": task.get("file_url"),
                "width": w,
                "height": h,
                "label": "pill_image",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            line = json.dumps(rec, ensure_ascii=False) + "\n"
            with write_lock:
                with labels_path.open("a", encoding="utf-8") as f:
                    f.write(line)

    return LabeledImageDownloader


REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_out_dir(p: Path) -> Path:
    if p.is_absolute():
        return p.resolve()
    return (REPO_ROOT / p).resolve()


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip().lower(), flags=re.UNICODE)
    return (s.strip("_") or "drug")[:100]


def load_drug_names(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if path.suffix.lower() == ".csv":
        rows: list[str] = []
        with path.open(encoding="utf-8-sig", newline="") as f:
            r = csv.DictReader(f)
            if r.fieldnames:
                lower = {x.lower(): x for x in r.fieldnames}
                col = None
                for key in ("drug", "name", "generic", "substance", "query"):
                    if key in lower:
                        col = lower[key]
                        break
                if col is None:
                    col = r.fieldnames[0]
                for row in r:
                    v = (row.get(col) or "").strip()
                    if v:
                        rows.append(v)
            return rows
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Tai anh pill/tablet bang icrawler (khong API key).")
    parser.add_argument("--drug", action="append", default=[], help="Ten thuoc (lap lai nhieu lan).")
    parser.add_argument("--drugs-file", type=Path, default=None, help="TXT mot dong mot ten hoac CSV.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "icrawler_pills",
        help="Thu muc goc; moi thuoc mot subfolder.",
    )
    parser.add_argument(
        "--engine",
        choices=("bing", "google"),
        default="bing",
        help="Bing: khuyen dung. Google: nhieu moi truong chi tra ve trang JS -> khong anh.",
    )
    parser.add_argument(
        "--query-template",
        type=str,
        default="{drug} pill tablet",
        help="Tu khoa tim kiem; dung {drug}.",
    )
    parser.add_argument("--max-num", type=int, default=100, help="So anh toi da / thuoc (neu khong dung --per-drug).")
    parser.add_argument(
        "--per-drug",
        type=int,
        default=None,
        metavar="N",
        help="So anh toi da cho MOI thuoc (ghi de --max-num). Vi du: 1 hoac 2.",
    )
    parser.add_argument(
        "--sleep-between-drugs",
        type=float,
        default=0.0,
        help="Giay nghi giua hai thuoc (goi y 0.3-0.8 khi list dai, giam risk chan).",
    )
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--min-size", type=int, nargs=2, metavar=("W", "H"), default=[200, 200], help="Loc anh nho.")
    parser.add_argument("--max-size", type=int, nargs=2, metavar=("W", "H"), default=None)
    parser.add_argument("--language", type=str, default=None, help="Vi du: en")
    parser.add_argument("--feeder-threads", type=int, default=1)
    parser.add_argument("--parser-threads", type=int, default=2)
    parser.add_argument("--downloader-threads", type=int, default=4)
    parser.add_argument(
        "--no-labels-file",
        action="store_true",
        help="Khong ghi labels.jsonl (mac dinh: co ghi).",
    )
    args = parser.parse_args()

    drugs: list[str] = list(args.drug)
    if args.drugs_file:
        drugs.extend(load_drug_names(args.drugs_file))
    drugs = [d.strip() for d in drugs if d.strip()]
    if not drugs:
        print("Can --drug hoac --drugs-file.")
        return 2

    max_per_drug = args.per_drug if args.per_drug is not None else args.max_num
    print(f"[INFO] {len(drugs)} thuoc, toi da {max_per_drug} anh/thuoc, sleep giua thuoc={args.sleep_between_drugs}s")

    out_root = _resolve_out_dir(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    min_size = tuple(args.min_size)
    max_size = tuple(args.max_size) if args.max_size else None

    label_lock = threading.Lock()

    for drug in drugs:
        keyword = args.query_template.format(drug=drug)
        sub = _slug(drug)
        drug_dir = out_root / sub
        root_dir = str(drug_dir)
        drug_dir.mkdir(parents=True, exist_ok=True)

        labels_path = drug_dir / "labels.jsonl"
        if not args.no_labels_file:
            labels_path.write_text("", encoding="utf-8")

        DownloaderCls = _make_labeled_image_downloader(
            drug=drug,
            query=keyword,
            engine=args.engine,
            sub_slug=sub,
            labels_path=labels_path,
            write_lock=label_lock,
        )

        print(f"=== {drug!r} -> {root_dir}")
        print(f"    engine={args.engine}, keyword: {keyword!r}, max_num={max_per_drug}")
        if not args.no_labels_file:
            print(f"    labels -> {labels_path}")
        if args.engine == "google":
            print(
                "    [WARN] Google Images thuong khong tra HTML anh cho bot (JS). "
                "Neu loi/0 anh, doi --engine bing."
            )

        common_kw = dict(
            feeder_threads=args.feeder_threads,
            parser_threads=args.parser_threads,
            downloader_threads=args.downloader_threads,
            storage={"root_dir": root_dir},
        )
        if not args.no_labels_file:
            common_kw["downloader_cls"] = DownloaderCls

        if args.engine == "bing":
            crawler = BingImageCrawler(parser_cls=RobustBingParser, **common_kw)
        else:
            crawler = GoogleImageCrawler(parser_cls=RobustGoogleParser, **common_kw)
        crawl_kw: dict = dict(
            keyword=keyword,
            offset=args.offset,
            max_num=max_per_drug,
            min_size=min_size,
            max_size=max_size,
        )
        if args.engine == "google" and args.language:
            crawl_kw["language"] = args.language
        crawler.crawl(**crawl_kw)
        if args.sleep_between_drugs > 0:
            time.sleep(args.sleep_between_drugs)

    print(f"Done. Output under: {out_root}")
    if not args.no_labels_file:
        print("Moi thu muc con co labels.jsonl: drug, query, filename, source_url, width, height.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
