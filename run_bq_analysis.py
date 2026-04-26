"""
Standalone script: run community detection on the BQ confidence question.
Uses the local paraphrase-multilingual-MiniLM-L12-v2 model for embeddings.
"""
import csv
import sys
import re
import os
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

CSV_PATH = "junk/bq-results-20260213-113630-1770982673076.csv"
QUESTION = "What more could Twinkl do to give you confidence?"
MODEL_PATH = "paraphrase-multilingual-MiniLM-L12-v2"
MIN_TEXT_LEN = 10
SIMILARITY_THRESHOLD = 0.62
MAX_NEIGHBORS = 12

# ── 1. Load data ──────────────────────────────────────────────────────────────
print("Loading data...")
with open(CSV_PATH, encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

texts_raw = [
    r["answer_value"].strip()
    for r in rows
    if r.get("main_title", "") == QUESTION and len(r.get("answer_value", "").strip()) >= MIN_TEXT_LEN
]
print(f"  {len(texts_raw)} substantive responses for '{QUESTION}'")

# ── 2. Deduplicate (case-insensitive) ─────────────────────────────────────────
seen: set[str] = set()
texts: list[str] = []
for t in texts_raw:
    key = t.casefold()
    if key not in seen:
        seen.add(key)
        texts.append(t)
print(f"  {len(texts)} after deduplication")

# ── 3. Embed ──────────────────────────────────────────────────────────────────
print("Embedding...")
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer(MODEL_PATH)
embeddings = model.encode(texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True)
print(f"  Embeddings shape: {embeddings.shape}")

# ── 4. Community detection (mirrors the app's pipeline exactly) ───────────────
print("Running community detection...")
os.chdir(os.path.join(os.path.dirname(__file__), "backend"))
sys.path.insert(0, ".")
from app.features.analysis.topic_analysis_services.community_detection_service import CommunityDetectionAnalysisService

svc = CommunityDetectionAnalysisService()
result = svc.run(
    embeddings,
    similarity_threshold=SIMILARITY_THRESHOLD,
    max_neighbors=MAX_NEIGHBORS,
    resolution=0.9,
    mutual_neighbors=False,
)
print(f"  Warnings: {result.warnings or 'none'}")

# ── 5. Group assembly ─────────────────────────────────────────────────────────
grouped: dict[int, list[str]] = defaultdict(list)
for text, assignment in zip(texts, result.assignments):
    grouped[int(assignment)].append(text)

total = len(texts)
# sort by size desc
ordered = sorted(grouped.items(), key=lambda kv: -len(kv[1]))

# ── 6. Keyword extraction (mirrors TopicAnalysisKeywordService) ───────────────
STOPWORDS = frozenset({
    "a","about","after","all","also","an","and","any","are","as","at","am","be","been",
    "being","both","but","by","can","could","do","does","each","few","for","from","had",
    "has","have","he","her","here","hers","him","his","how","i","if","in","into","is",
    "it","its","me","more","most","my","need","needs","not","of","on","only","or","other",
    "our","ours","out","own","please","really","same","she","should","so","that","the",
    "their","them","then","there","these","they","this","those","to","too","us","very",
    "was","we","were","what","when","which","who","will","with","would","you","your",
})
TOKEN_PAT = re.compile(r"[^\W_][^\W_'\-]*", re.UNICODE)

def top_terms(cluster_texts, top_n=5):
    counts: Counter[str] = Counter()
    for t in cluster_texts:
        for tok in TOKEN_PAT.findall(t.casefold()):
            tok = tok.strip("-'")
            if len(tok) > 2 and not tok.isdigit() and tok not in STOPWORDS:
                counts[tok] += 1
    return [term for term, _ in counts.most_common(top_n)]

# ── 7. Print results ──────────────────────────────────────────────────────────
n_communities = len(ordered)
noise = sum(1 for g_id, _ in ordered if g_id == -1)
singletons = sum(1 for _, members in ordered if len(members) == 1)
coverage_10plus = sum(len(m) for _, m in ordered if len(m) >= 10) / total * 100

print(f"\n{'='*70}")
print(f"RESULTS — '{QUESTION}'")
print(f"{'='*70}")
print(f"  Total responses (deduped): {total}")
print(f"  Communities found:         {n_communities}")
print(f"  Singletons:                {singletons}")
print(f"  Coverage in groups ≥10:    {coverage_10plus:.1f}%")
print()

for rank, (g_id, members) in enumerate(ordered[:20], 1):
    share = len(members) / total * 100
    terms = top_terms(members)
    label = " / ".join(terms[:3]) or f"Community {g_id}"
    print(f"  #{rank:2d}  [{len(members):4d} resp | {share:4.1f}%]  {label}")
    for ex in members[:2]:
        print(f"          » {ex[:100]}")
    print()

if len(ordered) > 20:
    rest = len(ordered) - 20
    rest_responses = sum(len(m) for _, m in ordered[20:])
    print(f"  ... {rest} more communities covering {rest_responses} responses")

# ── 8. Language breakdown ─────────────────────────────────────────────────────
try:
    from langdetect import detect
    langs: Counter[str] = Counter()
    for t in texts[:500]:
        try:
            langs[detect(t)] += 1
        except Exception:
            langs["unknown"] += 1
    print(f"\nLanguage sample (first 500):")
    for lang, count in langs.most_common(8):
        print(f"  {lang}: {count}")
except ImportError:
    pass
