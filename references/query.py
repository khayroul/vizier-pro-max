"""Deterministic query helpers over normalized local reference corpora."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable

from references.inventory import load_normalized_dataset
from references.search_engine import BM25Index


_DEFAULT_TOP_K = 5

REFERENCE_SEARCH_DATASETS: dict[str, tuple[tuple[str, str], ...]] = {
    "search_ui_styles": (
        ("ui_ux_pro_max", "ui_styles"),
        ("ui_ux_pro_max", "visual_motifs"),
    ),
    "search_ux_guidelines": (("ui_ux_pro_max", "ux_guidelines"),),
    "search_landing_patterns": (("ui_ux_pro_max", "landing_patterns"),),
    "search_typography_pairings": (("ui_ux_pro_max", "typography_pairings"),),
    "search_color_systems": (("ui_ux_pro_max", "color_systems"),),
    "search_chart_patterns": (
        ("ui_ux_pro_max", "chart_usage_patterns"),
        ("vega_lite", "chart_patterns"),
    ),
    "search_report_layouts": (
        ("quarto", "document_layout_options"),
        ("quarto", "table_figure_conventions"),
        ("quarto", "longform_structure_patterns"),
    ),
    "search_quarto_layouts": (
        ("quarto", "document_layout_options"),
        ("quarto", "callout_patterns"),
        ("quarto", "publishing_patterns"),
        ("quarto", "longform_structure_patterns"),
    ),
}


@dataclass(frozen=True)
class ReferenceSearchRecord:
    """Search document + payload pair for a normalized reference item."""

    record_id: str
    payload: dict[str, Any]
    search_text: str


class ReferenceQueryIndex:
    """Thin BM25 wrapper that returns normalized reference payloads."""

    def __init__(self, records: list[ReferenceSearchRecord]) -> None:
        self._payloads = {record.record_id: record.payload for record in records}
        documents = [
            {"record_id": record.record_id, "search_text": record.search_text}
            for record in records
        ]
        self._index = BM25Index(documents, ["search_text"])

    @property
    def size(self) -> int:
        """Return the number of indexed reference records."""
        return len(self._payloads)

    def search(self, query: str, *, top_k: int = _DEFAULT_TOP_K) -> list[dict[str, Any]]:
        """Search the index and return payloads with relevance scores."""
        results: list[dict[str, Any]] = []
        for match in self._index.search(query, top_k=top_k):
            record_id = str(match["record_id"])
            payload = deepcopy(self._payloads[record_id])
            payload["score"] = float(match["score"])
            results.append(payload)
        return results


def _as_search_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return " ".join(
            fragment
            for fragment in (_as_search_text(item) for item in value)
            if fragment
        )
    if isinstance(value, dict):
        return " ".join(
            fragment
            for fragment in (_as_search_text(item) for item in value.values())
            if fragment
        )
    return str(value)


def _dataset_items(family: str, dataset_id: str) -> list[dict[str, Any]]:
    payload = load_normalized_dataset(family, dataset_id)
    return list(payload.get("items", []))


def _annotate_item(
    item: dict[str, Any],
    *,
    family: str,
    dataset_id: str,
    source_datasets: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    payload = dict(item)
    payload["reference_family"] = family
    payload["dataset_id"] = dataset_id
    payload["source_datasets"] = [
        f"{source_family}/{source_dataset}"
        for source_family, source_dataset in source_datasets
    ]
    return payload


def _build_record(record_id: str, payload: dict[str, Any]) -> ReferenceSearchRecord:
    return ReferenceSearchRecord(
        record_id=record_id,
        payload=payload,
        search_text=_as_search_text(payload),
    )


def _build_dataset_records(
    source_datasets: tuple[tuple[str, str], ...],
) -> list[ReferenceSearchRecord]:
    records: list[ReferenceSearchRecord] = []
    for family, dataset_id in source_datasets:
        for index, item in enumerate(_dataset_items(family, dataset_id)):
            item_id = str(item.get("id", f"row-{index}"))
            payload = _annotate_item(
                item,
                family=family,
                dataset_id=dataset_id,
                source_datasets=((family, dataset_id),),
            )
            records.append(
                _build_record(
                    f"{family}:{dataset_id}:{item_id}",
                    payload,
                )
            )
    return records


def _build_ui_style_records() -> list[ReferenceSearchRecord]:
    source_datasets = REFERENCE_SEARCH_DATASETS["search_ui_styles"]
    motifs = {
        str(item["id"]): item
        for item in _dataset_items("ui_ux_pro_max", "visual_motifs")
    }
    records: list[ReferenceSearchRecord] = []
    for index, style in enumerate(_dataset_items("ui_ux_pro_max", "ui_styles")):
        style_id = str(style.get("id", f"row-{index}"))
        payload = _annotate_item(
            style,
            family="ui_ux_pro_max",
            dataset_id="ui_styles",
            source_datasets=source_datasets,
        )
        motif = motifs.get(style_id)
        if motif is not None:
            payload["visual_motif"] = motif
        records.append(_build_record(f"ui_ux_pro_max:ui_styles:{style_id}", payload))
    return records


_INDEX_BUILDERS: dict[str, Callable[[], list[ReferenceSearchRecord]]] = {
    "search_ui_styles": _build_ui_style_records,
    "search_ux_guidelines": lambda: _build_dataset_records(
        REFERENCE_SEARCH_DATASETS["search_ux_guidelines"]
    ),
    "search_landing_patterns": lambda: _build_dataset_records(
        REFERENCE_SEARCH_DATASETS["search_landing_patterns"]
    ),
    "search_typography_pairings": lambda: _build_dataset_records(
        REFERENCE_SEARCH_DATASETS["search_typography_pairings"]
    ),
    "search_color_systems": lambda: _build_dataset_records(
        REFERENCE_SEARCH_DATASETS["search_color_systems"]
    ),
    "search_chart_patterns": lambda: _build_dataset_records(
        REFERENCE_SEARCH_DATASETS["search_chart_patterns"]
    ),
    "search_report_layouts": lambda: _build_dataset_records(
        REFERENCE_SEARCH_DATASETS["search_report_layouts"]
    ),
    "search_quarto_layouts": lambda: _build_dataset_records(
        REFERENCE_SEARCH_DATASETS["search_quarto_layouts"]
    ),
}


@lru_cache(maxsize=None)
def get_reference_query_index(tool_name: str) -> ReferenceQueryIndex:
    """Return the cached index for a logical reference search tool."""
    try:
        builder = _INDEX_BUILDERS[tool_name]
    except KeyError as exc:
        msg = f"Unknown reference search tool: {tool_name}"
        raise KeyError(msg) from exc
    return ReferenceQueryIndex(builder())


def warm_reference_query_indices() -> dict[str, int]:
    """Build all cached reference query indices and return their sizes."""
    return {
        tool_name: get_reference_query_index(tool_name).size
        for tool_name in _INDEX_BUILDERS
    }


def search_ui_styles(query: str, *, top_k: int = _DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Search local UI style references enriched with visual motif data."""
    return get_reference_query_index("search_ui_styles").search(query, top_k=top_k)


def search_ux_guidelines(query: str, *, top_k: int = _DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Search local UX do/don't guidance from normalized corpora."""
    return get_reference_query_index("search_ux_guidelines").search(query, top_k=top_k)


def search_landing_patterns(query: str, *, top_k: int = _DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Search landing/hero CTA patterns from the local UI/UX corpus."""
    return get_reference_query_index("search_landing_patterns").search(query, top_k=top_k)


def search_typography_pairings(
    query: str,
    *,
    top_k: int = _DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    """Search typography pairing references from the local UI/UX corpus."""
    return get_reference_query_index("search_typography_pairings").search(
        query,
        top_k=top_k,
    )


def search_color_systems(query: str, *, top_k: int = _DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Search color system references from the local UI/UX corpus."""
    return get_reference_query_index("search_color_systems").search(query, top_k=top_k)


def search_chart_patterns(query: str, *, top_k: int = _DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Search chart heuristics and pattern references without invoking a runtime."""
    return get_reference_query_index("search_chart_patterns").search(query, top_k=top_k)


def search_report_layouts(query: str, *, top_k: int = _DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Search report-oriented layout references from the local Quarto corpus."""
    return get_reference_query_index("search_report_layouts").search(query, top_k=top_k)


def search_quarto_layouts(query: str, *, top_k: int = _DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Search Quarto-derived layout and publishing references without executing Quarto."""
    return get_reference_query_index("search_quarto_layouts").search(query, top_k=top_k)
