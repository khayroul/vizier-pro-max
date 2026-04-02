"""BM25 search engine over CSV design databases.

Indexes name, mood, and tags fields from palette/font CSV rows.
Returns top-k results with BM25 relevance scores.
Stdlib only — no external dependencies.
"""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path


_TOKENIZE_PATTERN = re.compile(r"[a-z0-9]+")
_HEX_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _tokenize(text: str) -> list[str]:
    """Lowercase and split text into alphanumeric tokens."""
    return _TOKENIZE_PATTERN.findall(text.lower())


def validate_hex(value: str) -> bool:
    """Check if a string is a valid CSS hex color."""
    return bool(_HEX_PATTERN.match(value))


class BM25Index:
    """BM25 index over a list of document dicts.

    Args:
        documents: List of dicts (CSV rows).
        fields: Which dict keys to index for search.
        k1: BM25 term frequency saturation parameter.
        b: BM25 document length normalization parameter.
    """

    def __init__(
        self,
        documents: list[dict[str, str]],
        fields: list[str],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._documents = documents
        self._fields = fields
        self._k1 = k1
        self._b = b

        # Tokenize each document
        self._doc_tokens: list[list[str]] = []
        for doc in documents:
            tokens: list[str] = []
            for field in fields:
                tokens.extend(_tokenize(doc.get(field, "")))
            self._doc_tokens.append(tokens)

        # Compute average document length
        total_tokens = sum(len(t) for t in self._doc_tokens)
        self._avgdl = total_tokens / len(documents) if documents else 1.0

        # Build inverse document frequency (IDF) table
        self._idf: dict[str, float] = {}
        num_docs = len(documents)
        term_doc_count: dict[str, int] = {}
        for tokens in self._doc_tokens:
            seen: set[str] = set()
            for token in tokens:
                if token not in seen:
                    term_doc_count[token] = term_doc_count.get(token, 0) + 1
                    seen.add(token)

        for term, doc_freq in term_doc_count.items():
            # Standard BM25 IDF formula
            self._idf[term] = math.log(
                (num_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0
            )

    def search(self, query: str, top_k: int = 5) -> list[dict[str, str | float]]:
        """Search the index and return top-k results with scores.

        If no terms match (all scores are 0), returns the first top_k
        documents as a fallback so the agent always has options.
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return self._fallback(top_k)

        scores: list[float] = []
        for idx, doc_tokens in enumerate(self._doc_tokens):
            score = 0.0
            doc_len = len(doc_tokens)
            # Count term frequencies in this document
            tf_map: dict[str, int] = {}
            for token in doc_tokens:
                tf_map[token] = tf_map.get(token, 0) + 1

            for q_token in query_tokens:
                if q_token not in self._idf:
                    continue
                tf = tf_map.get(q_token, 0)
                if tf == 0:
                    continue
                idf = self._idf[q_token]
                numerator = tf * (self._k1 + 1)
                denominator = tf + self._k1 * (
                    1 - self._b + self._b * doc_len / self._avgdl
                )
                score += idf * numerator / denominator
            scores.append(score)

        # Check if any scores are non-zero
        if max(scores) == 0.0:
            return self._fallback(top_k)

        # Sort by score descending, take top_k
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results: list[dict[str, str | float]] = []
        for idx, score in ranked[:top_k]:
            row: dict[str, str | float] = {**self._documents[idx]}
            row["score"] = round(score, 2)
            results.append(row)
        return results

    def _fallback(self, top_k: int) -> list[dict[str, str | float]]:
        """Return first top_k documents when no terms match."""
        results: list[dict[str, str | float]] = []
        for doc in self._documents[:top_k]:
            row: dict[str, str | float] = {**doc}
            row["score"] = 0.0
            results.append(row)
        return results


def load_csv(path: Path) -> list[dict[str, str]]:
    """Load a CSV file into a list of dicts."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
