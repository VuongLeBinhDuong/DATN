#!/usr/bin/env python3
"""
Crawl trang reference y khoa: benh (disease) va thuoc (drug) ra file JSON rieng.

Chay:
  python scripts/crawl_reference_pages.py --kind all
  python scripts/crawl_reference_pages.py --kind disease
  python scripts/crawl_reference_pages.py --kind drug
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]


def _seed_disease(topic_id: str, label: str, source_org: str, url: str) -> dict[str, str]:
    return {"topic_id": topic_id, "topic_type": "disease", "label": label, "source_org": source_org, "url": url}


def _seed_drug(topic_id: str, label: str, source_org: str, url: str) -> dict[str, str]:
    return {"topic_id": topic_id, "topic_type": "drug", "label": label, "source_org": source_org, "url": url}


# Moi chu de benh: nhieu seed URL / to chuc (MedlinePlus + CDC hoac NCI + WHO). Mo rong link con: --expand-links.
# Thuoc: crawl rieng file khac.
# Neu URL 404 sau nay, doi sang hub chu de tren cung site (vd cdc.gov/<chu-de>/).
SEEDS_DISEASE: list[dict[str, str]] = [
    _seed_disease("influenza", "Cum (Influenza)", "MedlinePlus", "https://medlineplus.gov/flu.html"),
    _seed_disease("influenza", "Cum (Influenza)", "CDC", "https://www.cdc.gov/flu/"),
    _seed_disease("influenza", "Cum (Influenza)", "WHO", "https://www.who.int/health-topics/influenza-seasonal"),
    _seed_disease("dengue", "Sot xuat huyet (Dengue)", "MedlinePlus", "https://medlineplus.gov/dengue.html"),
    _seed_disease("dengue", "Sot xuat huyet (Dengue)", "CDC", "https://www.cdc.gov/dengue/"),
    _seed_disease("dengue", "Sot xuat huyet (Dengue)", "WHO", "https://www.who.int/health-topics/dengue-and-severe-dengue"),
    _seed_disease("hypertension", "Tang huyet ap (Hypertension)", "MedlinePlus", "https://medlineplus.gov/highbloodpressure.html"),
    _seed_disease("hypertension", "Tang huyet ap (Hypertension)", "CDC", "https://www.cdc.gov/high-blood-pressure/"),
    _seed_disease("hypertension", "Tang huyet ap (Hypertension)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/hypertension"),
    _seed_disease("dm2", "Dai thao duong type 2", "MedlinePlus", "https://medlineplus.gov/type2diabetes.html"),
    _seed_disease("dm2", "Dai thao duong type 2", "CDC", "https://www.cdc.gov/diabetes/"),
    _seed_disease("dm2", "Dai thao duong type 2", "WHO", "https://www.who.int/news-room/fact-sheets/detail/diabetes"),
    _seed_disease("pneumonia", "Viem phoi (Pneumonia)", "MedlinePlus", "https://medlineplus.gov/pneumonia.html"),
    _seed_disease("pneumonia", "Viem phoi (Pneumonia)", "CDC", "https://www.cdc.gov/pneumonia/"),
    _seed_disease("pneumonia", "Viem phoi (Pneumonia)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/pneumonia"),
    _seed_disease("asthma", "Hen phe quan (Asthma)", "MedlinePlus", "https://medlineplus.gov/asthma.html"),
    _seed_disease("asthma", "Hen phe quan (Asthma)", "CDC", "https://www.cdc.gov/asthma/"),
    _seed_disease("asthma", "Hen phe quan (Asthma)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/asthma"),
    _seed_disease("copd", "COPD", "MedlinePlus", "https://medlineplus.gov/copd.html"),
    _seed_disease("copd", "COPD", "CDC", "https://www.cdc.gov/copd/"),
    _seed_disease("copd", "COPD", "WHO", "https://www.who.int/news-room/fact-sheets/detail/chronic-obstructive-pulmonary-disease-(copd)"),
    _seed_disease("hepatitis_b", "Viem gan B (Hepatitis B)", "MedlinePlus", "https://medlineplus.gov/hepatitisb.html"),
    _seed_disease("hepatitis_b", "Viem gan B (Hepatitis B)", "CDC", "https://www.cdc.gov/hepatitis-b/"),
    _seed_disease("hepatitis_b", "Viem gan B (Hepatitis B)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/hepatitis-b"),
    _seed_disease("covid19", "COVID-19", "MedlinePlus", "https://medlineplus.gov/coronavirusinfections.html"),
    _seed_disease("covid19", "COVID-19", "CDC", "https://www.cdc.gov/covid/"),
    _seed_disease("covid19", "COVID-19", "WHO", "https://www.who.int/news-room/fact-sheets/detail/coronavirus-disease-(covid-19)"),
    _seed_disease("stroke", "Dot quy (Stroke)", "MedlinePlus", "https://medlineplus.gov/stroke.html"),
    _seed_disease("stroke", "Dot quy (Stroke)", "CDC", "https://www.cdc.gov/stroke/"),
    _seed_disease("stroke", "Dot quy (Stroke)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/stroke"),
    _seed_disease("heart_disease", "Benh tim mach (Heart disease)", "MedlinePlus", "https://medlineplus.gov/heartdiseases.html"),
    _seed_disease("heart_disease", "Benh tim mach (Heart disease)", "CDC", "https://www.cdc.gov/heart-disease/"),
    _seed_disease("heart_disease", "Benh tim mach (Heart disease)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/cardiovascular-diseases-(cvds)"),
    _seed_disease("heart_attack", "Nhoi mau co tim (Heart attack)", "MedlinePlus", "https://medlineplus.gov/heartattack.html"),
    _seed_disease("heart_attack", "Nhoi mau co tim (Heart attack)", "CDC", "https://www.cdc.gov/heart-disease/about/heart-attack.html"),
    _seed_disease("heart_attack", "Nhoi mau co tim (Heart attack)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/cardiovascular-diseases-(cvds)"),
    _seed_disease("tb", "Lao (Tuberculosis)", "MedlinePlus", "https://medlineplus.gov/tuberculosis.html"),
    _seed_disease("tb", "Lao (Tuberculosis)", "CDC", "https://www.cdc.gov/tb/"),
    _seed_disease("tb", "Lao (Tuberculosis)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/tuberculosis"),
    _seed_disease("hiv", "HIV AIDS", "MedlinePlus", "https://medlineplus.gov/hiv.html"),
    _seed_disease("hiv", "HIV AIDS", "CDC", "https://www.cdc.gov/hiv/"),
    _seed_disease("hiv", "HIV AIDS", "WHO", "https://www.who.int/news-room/fact-sheets/detail/hiv-aids"),
    _seed_disease("malaria", "Sot ret (Malaria)", "MedlinePlus", "https://medlineplus.gov/malaria.html"),
    _seed_disease("malaria", "Sot ret (Malaria)", "CDC", "https://www.cdc.gov/malaria/"),
    _seed_disease("malaria", "Sot ret (Malaria)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/malaria"),
    _seed_disease("depression", "Tram cam (Depression)", "MedlinePlus", "https://medlineplus.gov/depression.html"),
    _seed_disease("depression", "Tram cam (Depression)", "CDC", "https://www.cdc.gov/mental-health/"),
    _seed_disease("depression", "Tram cam (Depression)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/depression"),
    _seed_disease("obesity", "Beo phi (Obesity)", "MedlinePlus", "https://medlineplus.gov/obesity.html"),
    _seed_disease("obesity", "Beo phi (Obesity)", "CDC", "https://www.cdc.gov/obesity/"),
    _seed_disease("obesity", "Beo phi (Obesity)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/obesity-and-overweight"),
    _seed_disease("diarrhea", "Tieu chay (Diarrhea)", "MedlinePlus", "https://medlineplus.gov/diarrhea.html"),
    _seed_disease("diarrhea", "Tieu chay (Diarrhea)", "CDC", "https://www.cdc.gov/healthywater/hygiene/disease/"),
    _seed_disease("diarrhea", "Tieu chay (Diarrhea)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/diarrhoeal-disease"),
    _seed_disease("dm1", "Dai thao duong type 1", "MedlinePlus", "https://medlineplus.gov/diabetestype1.html"),
    _seed_disease("dm1", "Dai thao duong type 1", "CDC", "https://www.cdc.gov/diabetes/about/about-type-1-diabetes.html"),
    _seed_disease("dm1", "Dai thao duong type 1", "WHO", "https://www.who.int/news-room/fact-sheets/detail/diabetes"),
    _seed_disease("hepatitis_c", "Viem gan C (Hepatitis C)", "MedlinePlus", "https://medlineplus.gov/hepatitisc.html"),
    _seed_disease("hepatitis_c", "Viem gan C (Hepatitis C)", "CDC", "https://www.cdc.gov/hepatitis-c/"),
    _seed_disease("hepatitis_c", "Viem gan C (Hepatitis C)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/hepatitis-c"),
    _seed_disease("hfmd", "Tay chan mieng (Hand foot mouth)", "MedlinePlus", "https://medlineplus.gov/handfootandmouthdisease.html"),
    _seed_disease("hfmd", "Tay chan mieng (Hand foot mouth)", "CDC", "https://www.cdc.gov/hand-foot-mouth/about/"),
    _seed_disease("measles", "Soi (Measles)", "MedlinePlus", "https://medlineplus.gov/measles.html"),
    _seed_disease("measles", "Soi (Measles)", "CDC", "https://www.cdc.gov/measles/"),
    _seed_disease("measles", "Soi (Measles)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/measles"),
    _seed_disease("lung_cancer", "Ung thu phoi", "MedlinePlus", "https://medlineplus.gov/lungcancer.html"),
    _seed_disease("lung_cancer", "Ung thu phoi", "NCI", "https://www.cancer.gov/types/lung"),
    _seed_disease("lung_cancer", "Ung thu phoi", "WHO", "https://www.who.int/news-room/fact-sheets/detail/cancer"),
    _seed_disease("breast_cancer", "Ung thu vu", "MedlinePlus", "https://medlineplus.gov/breastcancer.html"),
    _seed_disease("breast_cancer", "Ung thu vu", "NCI", "https://www.cancer.gov/types/breast"),
    _seed_disease("breast_cancer", "Ung thu vu", "WHO", "https://www.who.int/news-room/fact-sheets/detail/breast-cancer"),
    _seed_disease("colorectal_cancer", "Ung thu dai truc trang (Colorectal cancer)", "MedlinePlus", "https://medlineplus.gov/colorectalcancer.html"),
    _seed_disease("colorectal_cancer", "Ung thu dai truc trang (Colorectal cancer)", "NCI", "https://www.cancer.gov/types/colorectal"),
    _seed_disease("colorectal_cancer", "Ung thu dai truc trang (Colorectal cancer)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/cancer"),
    _seed_disease("headache", "Dau dau (Headache)", "MedlinePlus", "https://medlineplus.gov/headache.html"),
    _seed_disease("headache", "Dau dau (Headache)", "CDC", "https://www.cdc.gov/migraine/"),
    _seed_disease("headache", "Dau dau (Headache)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/headache-disorders"),
    _seed_disease("ckd", "Suy than man (Chronic kidney disease)", "MedlinePlus", "https://medlineplus.gov/kidneydisease.html"),
    _seed_disease("ckd", "Suy than man (Chronic kidney disease)", "CDC", "https://www.cdc.gov/kidney-disease/"),
    _seed_disease("ckd", "Suy than man (Chronic kidney disease)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/noncommunicable-diseases"),
    _seed_disease("epilepsy", "Dong kinh (Epilepsy)", "MedlinePlus", "https://medlineplus.gov/epilepsy.html"),
    _seed_disease("epilepsy", "Dong kinh (Epilepsy)", "CDC", "https://www.cdc.gov/epilepsy/"),
    _seed_disease("epilepsy", "Dong kinh (Epilepsy)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/epilepsy"),
    _seed_disease("arthritis", "Viem khop (Arthritis)", "MedlinePlus", "https://medlineplus.gov/arthritis.html"),
    _seed_disease("arthritis", "Viem khop (Arthritis)", "CDC", "https://www.cdc.gov/arthritis/"),
    _seed_disease("arthritis", "Viem khop (Arthritis)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/musculoskeletal-conditions"),
    _seed_disease("allergies", "Di ung (Allergies)", "MedlinePlus", "https://medlineplus.gov/allergies.html"),
    _seed_disease("allergies", "Di ung (Allergies)", "CDC", "https://www.cdc.gov/allergies/"),
    _seed_disease("allergies", "Di ung (Allergies)", "WHO", "https://www.who.int/news-room/fact-sheets/detail/asthma"),
]

SEEDS_DRUG: list[dict[str, str]] = [
    # Chu de thuoc (khong tron crawl voi benh)
    _seed_drug("topic_pain_otc", "Thuoc: Giam dau OTC (Pain relievers, NSAID)", "MedlinePlus", "https://medlineplus.gov/painrelievers.html"),
    _seed_drug("topic_pain_otc", "Thuoc: Giam dau OTC (Pain relievers, NSAID)", "FDA", "https://www.fda.gov/drugs/resources-drugs/information-consumers-and-patients-drugs"),
    _seed_drug("topic_pain_otc", "Thuoc: Giam dau OTC (Pain relievers, NSAID)", "WHO", "https://www.who.int/health-topics/medicines"),
    _seed_drug("topic_antibiotics", "Thuoc: Khang sinh (Antibiotics)", "MedlinePlus", "https://medlineplus.gov/antibiotics.html"),
    _seed_drug("topic_antibiotics", "Thuoc: Khang sinh (Antibiotics)", "CDC", "https://www.cdc.gov/antibiotic-use/"),
    _seed_drug("topic_antibiotics", "Thuoc: Khang sinh (Antibiotics)", "WHO", "https://www.who.int/health-topics/antimicrobial-resistance"),
    _seed_drug("topic_otc", "Thuoc: Thuoc khong ke don (OTC)", "MedlinePlus", "https://medlineplus.gov/ency/article/002208.htm"),
    _seed_drug("topic_otc", "Thuoc: Thuoc khong ke don (OTC)", "CDC", "https://www.cdc.gov/medicationsafety/index.html"),
    _seed_drug("topic_otc", "Thuoc: Thuoc khong ke don (OTC)", "FDA", "https://www.fda.gov/drugs/information-consumers-and-patients-drugs/buying-using-medicine-safely"),
    _seed_drug("topic_otc", "Thuoc: Thuoc khong ke don (OTC)", "WHO", "https://www.who.int/health-topics/substandard-and-falsified-medical-products"),
    _seed_drug("topic_abuse", "Thuoc: Lam dung thuoc ke don", "MedlinePlus", "https://medlineplus.gov/prescriptiondrugabuse.html"),
    _seed_drug("topic_abuse", "Thuoc: Lam dung thuoc ke don", "CDC", "https://www.cdc.gov/drugoverdose/index.html"),
    _seed_drug("topic_abuse", "Thuoc: Lam dung thuoc ke don", "FDA", "https://www.fda.gov/drugs/information-drug-class/opioid-medications"),
    _seed_drug("topic_abuse", "Thuoc: Lam dung thuoc ke don", "WHO", "https://www.who.int/health-topics/drugs-psychoactive"),
    # Monograph (MedlinePlus druginfo/meds)
    _seed_drug("drug_paracetamol", "Thuoc: Paracetamol (Acetaminophen)", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a681004.html"),
    _seed_drug("drug_ibuprofen", "Thuoc: Ibuprofen", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a682159.html"),
    _seed_drug("drug_aspirin", "Thuoc: Aspirin (Acetylsalicylic acid)", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a682878.html"),
    _seed_drug("drug_metformin", "Thuoc: Metformin", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a696005.html"),
    _seed_drug("drug_amoxicillin", "Thuoc: Amoxicillin", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a685001.html"),
    _seed_drug("drug_lisinopril", "Thuoc: Lisinopril", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a692051.html"),
    _seed_drug("drug_atorvastatin", "Thuoc: Atorvastatin", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a600045.html"),
    _seed_drug("drug_albuterol", "Thuoc: Albuterol (Salbutamol)", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a607004.html"),
    _seed_drug("drug_levothyroxine", "Thuoc: Levothyroxine", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a682461.html"),
    _seed_drug("drug_azithromycin", "Thuoc: Azithromycin", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a697037.html"),
    _seed_drug("drug_prednisone", "Thuoc: Prednisone", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a601102.html"),
    _seed_drug("drug_hctz", "Thuoc: Hydrochlorothiazide", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a682571.html"),
    _seed_drug("drug_sertraline", "Thuoc: Sertraline", "MedlinePlus", "https://medlineplus.gov/druginfo/meds/a697048.html"),
]

WS_RE = re.compile(r"\s+")
BAD_EXT_RE = re.compile(r"\.(jpg|jpeg|png|gif|svg|pdf|mp4|zip|docx?)$", re.IGNORECASE)
GENERIC_QUERY_TERMS = [
    "symptom",
    "treatment",
    "diagnosis",
    "prevention",
    "cause",
    "risk",
    "drug",
    "medication",
    "medicine",
    "prescription",
    "dosage",
    "interaction",
    "antibiotic",
    "vitamin",
    "generic",
    "tablet",
    "pharmacist",
    "side",
    "effect",
]


def clean_text(text: str) -> str:
    return WS_RE.sub(" ", unescape(text)).strip()


def extract_main_text(soup: BeautifulSoup) -> tuple[str, str]:
    for bad in soup(["script", "style", "noscript"]):
        bad.decompose()

    title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    parts: list[str] = []

    main = soup.find("main") or soup.find("article") or soup.body
    if main is None:
        return title, ""

    for tag in main.find_all(["h1", "h2", "h3", "p", "li"]):
        txt = clean_text(tag.get_text(" ", strip=True))
        if len(txt) < 30:
            continue
        parts.append(txt)

    merged = "\n".join(parts)
    return title, merged


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    parsed = parsed._replace(query="", fragment="")
    return urlunparse(parsed)


def same_domain(a: str, b: str) -> bool:
    na = urlparse(a).netloc.lower()
    nb = urlparse(b).netloc.lower()
    return na == nb


def _seed_label(seed: dict[str, str]) -> str:
    return (seed.get("label") or seed.get("disease") or "").strip()


def keyword_set(seed: dict[str, str]) -> set[str]:
    label = _seed_label(seed)
    disease_terms = re.findall(r"[a-zA-Z0-9]+", label.lower())
    return set(disease_terms + GENERIC_QUERY_TERMS)


def extract_candidate_links(
    soup: BeautifulSoup,
    base_url: str,
    seed: dict[str, str],
    max_links: int,
) -> list[str]:
    keys = keyword_set(seed)
    out: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        full = normalize_url(urljoin(base_url, href))
        if not full.startswith("http"):
            continue
        if not same_domain(full, base_url):
            continue
        if BAD_EXT_RE.search(full):
            continue
        # Ignore navigational anchors
        if full.endswith("/") and full.count("/") <= 3:
            continue

        anchor_text = clean_text(a.get_text(" ", strip=True)).lower()
        target_text = (anchor_text + " " + full.lower())
        if not any(k in target_text for k in keys):
            continue
        if full in seen:
            continue

        seen.add(full)
        out.append(full)
        if len(out) >= max_links:
            break
    return out


def crawl_url(seed: dict[str, str], target_url: str, timeout: int) -> tuple[dict[str, Any], BeautifulSoup]:
    resp = requests.get(
        target_url,
        timeout=timeout,
        headers={"User-Agent": "medical-reference-crawler/1.0"},
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    title, content = extract_main_text(soup)
    label = _seed_label(seed)
    return ({
        "topic_id": seed["topic_id"],
        "topic_type": seed["topic_type"],
        "disease": label,
        "source_org": seed["source_org"],
        "source_url": target_url,
        "title": title,
        "content": content,
        "content_type": "reference_page",
        "lang": "en",
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }, soup)


def run_crawl(
    seeds: list[dict[str, str]],
    *,
    timeout: int,
    expand_links: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for seed in seeds:
        try:
            rec, soup = crawl_url(seed, target_url=seed["url"], timeout=timeout)
            if len(rec["content"]) < 300:
                print(f"[WARN] Too short: {seed['url']}")
            else:
                rows.append(rec)
                seen_urls.add(normalize_url(seed["url"]))
                print(f"[OK] {seed['source_org']} - {_seed_label(seed)} (seed)")

            if expand_links > 0:
                links = extract_candidate_links(
                    soup=soup,
                    base_url=seed["url"],
                    seed=seed,
                    max_links=expand_links,
                )
                for link in links:
                    if link in seen_urls:
                        continue
                    try:
                        child_rec, _ = crawl_url(seed, target_url=link, timeout=timeout)
                        if len(child_rec["content"]) < 300:
                            continue
                        rows.append(child_rec)
                        seen_urls.add(link)
                        print(f"[OK]   + child: {link}")
                    except Exception:
                        continue
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Failed {seed['url']}: {exc}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crawl reference: benh va thuoc ra file rieng.",
    )
    parser.add_argument(
        "--kind",
        choices=("disease", "drug", "all"),
        default="all",
        help="disease: chi benh; drug: chi thuoc; all: hai file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "data",
        help="Thu muc ghi medical_reference_diseases.json / medical_reference_drugs.json (khi --kind all).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ghi mot file JSON (dung voi --kind disease hoac drug; bo qua --output-dir).",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--expand-links", type=int, default=3, help="So link con crawl them moi seed.")
    args = parser.parse_args()

    if args.kind == "all":
        out_dir = args.output_dir
        out_dis = out_dir / "medical_reference_diseases.json"
        out_drug = out_dir / "medical_reference_drugs.json"
        print("=== Crawl benh (disease) ===")
        rows_d = run_crawl(SEEDS_DISEASE, timeout=args.timeout, expand_links=args.expand_links)
        out_dis.parent.mkdir(parents=True, exist_ok=True)
        out_dis.write_text(json.dumps(rows_d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved {len(rows_d)} records to: {out_dis.resolve()}")
        print("=== Crawl thuoc (drug) ===")
        rows_g = run_crawl(SEEDS_DRUG, timeout=args.timeout, expand_links=args.expand_links)
        out_drug.write_text(json.dumps(rows_g, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved {len(rows_g)} records to: {out_drug.resolve()}")
        return 0

    if args.kind == "disease":
        out = args.output or (args.output_dir / "medical_reference_diseases.json")
        rows = run_crawl(SEEDS_DISEASE, timeout=args.timeout, expand_links=args.expand_links)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved {len(rows)} records to: {out.resolve()}")
        return 0

    out = args.output or (args.output_dir / "medical_reference_drugs.json")
    rows = run_crawl(SEEDS_DRUG, timeout=args.timeout, expand_links=args.expand_links)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} records to: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
