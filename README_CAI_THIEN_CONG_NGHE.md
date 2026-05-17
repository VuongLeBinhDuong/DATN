# Danh gia he thong hoi dap va huong cai thien cong nghe

Tai lieu nay tap trung vao danh gia **chat luong cong nghe** cua he thong hoi dap (dac biet Retrieval va QA quality), khong di sau vao ha tang/van hanh.

---

## 1) Nhan xet nhanh ve he thong hien tai

## Diem manh

- Da co kien truc tach lop ro rang: `api` -> `services` -> `repositories`.
- Co 2 mode retrieval tri thuc (`neo4j` + `cli` fallback), giup he thong khong bi "die" khi 1 backend gap su co.
- Da co danh gia retrieval voi metric chuan (`Precision/Recall/F1/MRR/NDCG`) trong `scripts/eval_retrieval_quality.py`.
- Da co confidence heuristic (`agent/retrieval_confidence.py`) de phan loai muc tin cay cho UI.
- Da co nguon graph context + source titles tu Neo4j (`repositories/neo4j_repo.py`), la nen tang tot de nang cap retrieval.

## Diem can nang cap gap

- Retrieval hien tai nghieng nhieu vao graph/fulltext, chua co pipeline **hybrid retrieval + rerank** day du.
- Confidence hien tai van la heuristic tay, chua duoc calibrate theo tap eval.
- Chua co co che query rewriting/decomposition on dinh cho cau hoi da thuc the (multi-hop).
- Eval co kha nang bi "nhieu" neu `expected_nodes/edges` trong dataset khong khop graph that.
- Chua tach ro "retrieval quality" va "answer quality" thanh hai bo metric rieng, de quan sat tien bo.

---

## 2) Muc tieu cai thien cong nghe (uu tien retrieval)

Muc tieu 1: tang Recall@K nhung khong lam giam Precision@K qua muc.

Muc tieu 2: giam hallucination bang cach tang chat luong context dua vao LLM.

Muc tieu 3: tang kha nang tra loi cau hoi phuc hop (thuoc-tuong tac-benh, trieu chung-chan doan-chi dinh).

Muc tieu 4: co dashboard metric ro rang de biet nang cap nao thuc su hieu qua.

---

## 3) Roadmap cai thien theo pha

## Pha A - On dinh retrieval nen tang (ngan han)

1. Chuan hoa truy van va scoring
- Thong nhat preprocessing query (lowercase, bo ky tu dac biet, chuan hoa tieng Viet co dau/khong dau neu can).
- Luu metadata score theo nguon (`fulltext_score`, `neighbor_score`, `rank`).

2. Calibrate confidence
- Dung ket qua eval de map confidence "cao/trung/thap" theo nguong du lieu that.
- Ghi lai confidence va ket qua cuoi de fine-tune nguong theo tuan.

3. Don dep eval dataset
- Bat buoc chay validate dataset vs Neo4j truoc khi chot metric.
- Tach report: metric retrieval vs metric answer.

Cong nghe de ap dung:
- Scikit-learn/isotonic regression hoac logistic calibration (nhe) cho confidence.
- Pandas + notebook report de theo doi drift metric.

---

## Pha B - Nang cap retrieval chat luong cao (trung han)

1. Hybrid retrieval 3 nhanh
- Graph retrieval: Neo4j (dang co).
- Lexical retrieval: BM25/OpenSearch.
- Semantic retrieval: Milvus + embedding.

2. Fusion va rerank
- Dung weighted fusion (RRF hoac weighted score merge).
- Dung cross-encoder reranker cho top-N ung vien truoc khi cap context cho LLM.

3. Context packing thong minh
- Gom top chunks theo da dang nguon, tranh trung lap.
- Gioi han token theo budget; uu tien chunk co score va do bao phu thuc the cao.

Cong nghe de ap dung:
- `rank-bm25` (de thu nhanh) hoac OpenSearch/Elasticsearch (production retrieval lexical).
- Cross-encoder reranker (vi du `ms-marco-MiniLM-L-6-v2`).
- RRF (Reciprocal Rank Fusion) de gop ket qua tu graph/lexical/semantic.

---

## Pha C - Multi-hop va query intelligence

1. Query rewriting
- Sinh 2-4 retrieval queries bo tro tu cau hoi goc.
- Chon query tot nhat dua tren confidence.

2. Multi-hop decomposition
- Tach cau hoi phuc hop thanh sub-queries:
  - Tim thuc the.
  - Tim quan he.
  - Kiem tra rang buoc bo sung.
  - Tong hop ket luan.

3. Answer groundedness check
- Kiem tra moi claim trong answer co bang chung trong source/context.
- Neu claim khong co chung cu, ha muc tu tin hoac them canh bao.

Cong nghe de ap dung:
- LangGraph state machine cho decomposition.
- LLM structured outputs (JSON schema) de giam parse loi.
- Claim-evidence matching (cross-encoder NLI hoac lightweight judge model).

---

## 4) KPI de do hieu qua cai thien

Nen theo doi toi thieu:

- Retrieval:
  - Precision@K, Recall@K, F1@K, MRR, NDCG@K
  - % cau hoi co it nhat 1 source score cao
- Answer:
  - Groundedness (ti le claim co chung cu)
  - Faithfulness error rate
  - Answer completeness (bao phu y chinh)
- Trải nghiệm:
  - Ty le "khong tra loi duoc"
  - Ty le user hoi lai cung mot y

Muc tieu tham khao (co the dieu chinh):

- Precision@5 >= 0.75
- Recall@10 >= 0.80
- Groundedness >= 0.85

---

## 5) De xuat uu tien theo effort/impact

## Uu tien cao - effort vua

1. Validate eval dataset + chuan hoa report retrieval/answer tach biet.
2. Ap dung fusion don gian (graph + lexical) truoc, chua can full stack.
3. Them reranker cho top-20 -> top-5.

## Uu tien cao - effort cao

4. Multi-hop decomposition cho nhom cau hoi phuc hop.
5. Groundedness checker theo claim.

## Uu tien trung binh

6. Query rewriting co kiem soat.
7. Calibrate confidence theo du lieu that.

---

## 6) Ke hoach thuc thi goi y (6-8 tuan)

Tuan 1-2:
- Chuan hoa eval + confidence calibration ban dau.
- Chot baseline metric.

Tuan 3-4:
- Hybrid retrieval (graph + lexical) + fusion.
- Danh gia truoc/sau bang cung bo eval.

Tuan 5-6:
- Them cross-encoder reranker.
- Toi uu context packing.

Tuan 7-8:
- Multi-hop decomposition cho nhom cau hoi kho.
- Groundedness checker va policy fallback.

---

## 7) Ket luan

He thong hien tai co nen tang tot va dung huong cho do an hoi dap y khoa. De nang cap chat luong that su, trong tam nen dat vao:

1. Retrieval hybrid + rerank.
2. Multi-hop decomposition cho cau hoi phuc hop.
3. Groundedness va confidence duoc do luong, calibrate bang metric.

Neu lam tot 3 nhom nay, chat luong tra loi se tang ro hon nhieu so voi viec dau tu them vao ha tang o giai doan hien tai.
