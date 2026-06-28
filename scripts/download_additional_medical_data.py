from __future__ import annotations

import json
from pathlib import Path
from datasets import load_dataset  # type: ignore

def main():
    print("Loading dataset from Hugging Face...")
    # Load the dataset
    ds = load_dataset("quannguyen204/vietnamese-medical-article-corpus", split="train")
    
    print(f"Total rows in dataset: {len(ds)}")
    
    # We want about 1/3 of ViHealthQA (which is around 10k total records), so ~3300 records
    target_count = 10000
    sub_ds = ds.select(range(min(target_count, len(ds))))
    
    records = []
    for idx, row in enumerate(sub_ds):
        # Map fields to a clean informational structure
        title = str(row.get("question") or f"Bài viết y học {idx}").strip()
        content = str(row.get("answer") or "").strip()
        
        # Avoid empty content
        if not content:
            continue
            
        records.append({
            "topic_id": f"article_corp_{idx}",
            "title": title[:200],
            "content": content,
            "source_org": "VietnameseMedicalCorpus",
            "lang": "vi"
        })
        
    out_dir = Path("data/additional_data")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "medical_articles.json"
    
    # Save as JSON list
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully saved {len(records)} records to {out_file}")

if __name__ == "__main__":
    main()
