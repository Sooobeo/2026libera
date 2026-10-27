"""v6.3 actual BM25 retrieval with explicit evidence and tokenizer boundaries.

No tokenizer is guessed. Production callers must provide the frozen model's exact
token counter. Engineering tests may supply an explicitly marked test counter.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
DEPS = ROOT / "tmp" / "v63_python_deps"
if DEPS.exists():
    sys.path.insert(0, str(DEPS))
from rank_bm25 import BM25Okapi

INDUSTRIES = ("NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq", "Telcm", "Utils", "Shops", "Hlth", "Money", "Other")
INDUSTRY_NAMES = ("Consumer Nondurables", "Consumer Durables", "Manufacturing", "Energy", "Chemicals", "Business Equipment", "Telecommunications", "Utilities", "Shops", "Healthcare", "Finance", "Other")
QUERY = "investment outlook expected return forecast uncertainty risk portfolio industry " + " ".join(INDUSTRY_NAMES)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def lexical_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass(frozen=True)
class TokenCounter:
    identity: str
    count: Callable[[str], int]
    exact_model_tokenizer: bool


@dataclass(frozen=True)
class AtomicUnit:
    text: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Document:
    document_id: str
    fund_id: str  # COMMON or exactly the current fund
    publication_date: str
    period: str  # development, A, B, C
    kind: str  # forecast_memo, method_note, fund_facts, official_text
    header: str
    units: tuple[AtomicUnit, ...]
    source_url: str = ""

    @property
    def text(self):
        return self.header + "\n" + "\n".join(u.text for u in self.units)

    @property
    def source_sha256(self):
        return sha(self.text)


def eligible_documents(documents, fund_id, cutoff, period):
    """Filter before BM25 fitting, not after ranking. C-only text cannot enter A/B."""
    date.fromisoformat(cutoff)
    selected, seen, ids = [], set(), set()
    for doc in sorted(documents, key=lambda d: d.document_id):
        date.fromisoformat(doc.publication_date)
        if doc.document_id in ids:
            raise ValueError("Duplicate document ID")
        ids.add(doc.document_id)
        if doc.kind not in {"forecast_memo", "method_note", "fund_facts", "official_text"}:
            raise ValueError("Evaluator-only or unknown corpus kind")
        if doc.fund_id not in {"COMMON", fund_id} or doc.publication_date > cutoff:
            continue
        if doc.period not in {period, "common"}:
            continue
        if period == "C" and doc.kind == "official_text" and doc.publication_date <= "2026-03-31":
            continue  # continuing mandates belong in common baseline, not C new-outlook recall
        if doc.source_sha256 not in seen:
            selected.append(doc)
            seen.add(doc.source_sha256)
    return selected


def chunk_document(doc: Document, counter: TokenCounter, limit=400, overlap=50):
    """Whole atomic rows, repeated header, whole-unit overlap <= 50 model tokens.

    A single oversized atomic unit fails closed instead of cutting a numeric row,
    its precision, date, unit, or footnote. Upstream extraction must identify units.
    """
    if not doc.units:
        raise ValueError("Document contains no atomic units")
    chunks, start = [], 0
    while start < len(doc.units):
        stop = start
        while stop < len(doc.units):
            candidate = doc.header + "\n" + "\n".join(u.text for u in doc.units[start:stop + 1])
            if counter.count(candidate) > limit:
                break
            stop += 1
        if stop == start:
            raise ValueError(f"Atomic unit exceeds {limit} exact tokenizer tokens: {doc.document_id}:{start}")
        selected = doc.units[start:stop]
        text = doc.header + "\n" + "\n".join(u.text for u in selected)
        chunks.append({"chunk_id": f"{doc.document_id}:{start:04d}-{stop:04d}",
                       "document_id": doc.document_id, "paragraph_order": start,
                       "unit_indices": list(range(start, stop)), "text": text,
                       "text_sha256": sha(text), "source_sha256": doc.source_sha256,
                       "tokens": counter.count(text),
                       "evidence_ids": sorted({e for u in selected for e in u.evidence_ids})})
        if stop == len(doc.units):
            break
        next_start = stop
        # At least one new unit must be consumed on every iteration.
        for i in range(stop - 1, start, -1):
            if counter.count("\n".join(u.text for u in doc.units[i:stop])) <= overlap:
                next_start = i
            else:
                break
        start = next_start
    return chunks


def retrieve(documents, fund_id, cutoff, period, counter: TokenCounter, *, engineering=False,
             gold_ids=()):
    if not counter.exact_model_tokenizer and not engineering:
        raise ValueError("Frozen exact model tokenizer is required")
    if importlib.metadata.version("rank-bm25") != "0.2.2":
        raise ValueError("rank-bm25 version drift")
    eligible = eligible_documents(documents, fund_id, cutoff, period)
    chunks = [c for d in eligible for c in chunk_document(d, counter)]
    if not chunks:
        raise ValueError("No eligible chunks")
    terms = [lexical_tokens(c["text"]) for c in chunks]
    if any(not t for t in terms):
        raise ValueError("Empty lexical chunk")
    engine = BM25Okapi(terms, k1=1.5, b=0.75, epsilon=0.25)
    scores = engine.get_scores(lexical_tokens(QUERY))
    ranked = sorted(range(len(chunks)), key=lambda i: (-float(scores[i]), chunks[i]["document_id"], chunks[i]["paragraph_order"]))
    chosen = ranked[:4]
    # Render in rank order but merge duplicate atomic source units; evidence is not counted twice.
    doc_map = {d.document_id: d for d in eligible}
    seen_units, packet_parts, recovered = set(), [], set()
    for i in chosen:
        chunk, remaining = chunks[i], []
        doc = doc_map[chunk["document_id"]]
        for j in chunk["unit_indices"]:
            key = (doc.source_sha256, j)
            if key not in seen_units:
                remaining.append(doc.units[j].text)
                recovered.update(doc.units[j].evidence_ids)
                seen_units.add(key)
        if remaining:
            packet_parts.append(f"[Document {doc.document_id}]\n" + doc.header + "\n" + "\n".join(remaining))
    packet = "\n\n".join(packet_parts)
    full = "\n\n".join(f"[Document {d.document_id}]\n{d.text}" for d in eligible)
    all_units = {(d.source_sha256, j) for d in eligible for j in range(len(d.units))}
    packet_record = {"text": packet, "sha256": sha(packet), "tokens": counter.count(packet),
                     "exposed_evidence_ids": sorted(recovered)}
    manifest = [{"document_id": d.document_id, "source_sha256": d.source_sha256,
                 "publication_date": d.publication_date, "fund_id": d.fund_id,
                 "period": d.period, "kind": d.kind, "source_url": d.source_url} for d in eligible]
    gold = set(gold_ids)
    return {"engineering_only": engineering, "engine": "rank-bm25==0.2.2/BM25Okapi",
            "query": QUERY, "parameters": {"k1": 1.5, "b": 0.75, "epsilon": 0.25, "top_k": 4},
            "tokenizer": {"identity": counter.identity, "exact": counter.exact_model_tokenizer},
            "fund_id": fund_id, "period": period, "cutoff": cutoff,
            "corpus_manifest": manifest, "corpus_sha256": sha(canonical(manifest)),
            "eligible_ids": [d.document_id for d in eligible],
            "all_chunk_scores": [{"chunk_id": chunks[i]["chunk_id"], "score": float(scores[i]),
                                  "text_sha256": chunks[i]["text_sha256"], "tokens": chunks[i]["tokens"]} for i in ranked],
            "ranked_chunk_ids": [chunks[i]["chunk_id"] for i in chosen],
            "packet": packet_record,
            "full": {"text": full, "sha256": sha(full), "tokens": counter.count(full),
                     "exposed_evidence_ids": sorted({e for d in eligible for u in d.units for e in u.evidence_ids})},
            "diagnostics_evaluator_only": {"gold_recall_at_4": len(recovered & gold) / len(gold) if gold else None,
                                           "gold_unit_count": len(gold), "recovered_gold_count": len(recovered & gold),
                                           "same_bytes_as_full": packet == full,
                                           "same_atomic_content_as_full": seen_units == all_units}}


def b_documents(fund_id, scenario_id, x, precision, as_of, audited_fund_facts, *, period="B"):
    """Three fixed B documents; inputs contain only this fund's visible facts.

    The caller must supply already roundtripped x and audited baseline facts.
    No theta, other-fund signals, oracle, gold annotations or future return exists
    in this signature. Numeric gold metadata travels only as evidence IDs.
    """
    if len(x) != 12 or precision not in (0.5, 1.0, 2.0):
        raise ValueError("Invalid forecast dimension/precision")
    date.fromisoformat(as_of)
    prefix = f"{scenario_id}/{fund_id}"
    header = (f"SYNTHETIC CONTROLLED FORECAST; not this fund's internal outlook. Fund {fund_id}. "
              f"Date {as_of}. Unit decimal monthly total return. Observation precision r={precision:g}; "
              "private error covariance Omega_i=V0/r. Errors independent of common observation error conditional on latent return. "
              "The latent return is not observed. Investment outlook expected return forecast uncertainty risk portfolio industry.")
    units = tuple(AtomicUnit(f"{code} ({name}): forecast x={float(value):.10f}; evidence_id={prefix}/X/{code}",
                             (f"{prefix}/X/{code}",)) for code, name, value in zip(INDUSTRIES, INDUSTRY_NAMES, x))
    facts_units=(AtomicUnit(audited_fund_facts),) if isinstance(audited_fund_facts,str) else tuple(audited_fund_facts)
    if not facts_units or any(not isinstance(unit,AtomicUnit) for unit in facts_units):
        raise ValueError('Fund facts must contain intact atomic facts.')
    return [Document(prefix + "/forecast_memo", fund_id, as_of, period, "forecast_memo", header, units),
            Document(prefix + "/method_note", fund_id, as_of, period, "method_note", "Synthetic observation method.",
                     (AtomicUnit("The common observation y and this fund's private x are noisy observations of the same latent return. "
                                 "Their errors are conditionally independent. Prior covariance V0=Sigma/12; common error covariance Omega0=V0. "
                                 "Larger disclosed r means greater precision. Missing observations or precision cannot be invented."),)),
            Document(prefix + "/fund_facts", fund_id, as_of, period, "fund_facts", "Mandatory baseline; already supplied to every arm.",
                     facts_units)]
