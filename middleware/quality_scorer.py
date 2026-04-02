"""Property-based quality scoring per pipeline.

Replaces hardcoded 8.0 self-grades with measurable property checks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class QualityProperty:
    """A single measurable quality property."""

    name: str
    passed: bool
    pass_delta: float
    fail_delta: float
    detail: str
    is_gate: bool = False


@dataclass(frozen=True)
class QualityScore:
    """Composite quality score from property checks."""

    score: float
    passed: bool
    properties: list[QualityProperty]
    pipeline: str


def compute_score(
    properties: list[QualityProperty],
    *,
    pipeline: str,
    base: float = 5.0,
) -> QualityScore:
    """Compute composite score from quality properties.

    Args:
        properties: List of quality properties to evaluate.
        pipeline: Name of the pipeline being scored.
        base: Starting score before applying deltas.

    Returns:
        QualityScore with final clamped score and pass/fail status.
    """
    score = base
    gate_failed = False

    for prop in properties:
        if prop.passed:
            score += prop.pass_delta
        else:
            score -= prop.fail_delta
            if prop.is_gate:
                gate_failed = True

    if gate_failed:
        score = min(score, 4.0)

    score = max(1.0, min(10.0, score))
    return QualityScore(
        score=score,
        passed=score >= 7.0,
        properties=list(properties),
        pipeline=pipeline,
    )


def score_competitive_analysis(
    report: str,
    chart_paths: list[Path],
) -> QualityScore:
    """Score a competitive analysis report.

    Args:
        report: The text content of the report.
        chart_paths: Paths to chart image files.

    Returns:
        QualityScore for this competitive analysis output.
    """
    properties: list[QualityProperty] = []

    # Named competitors: capitalized names, filter out short section headers
    competitor_pattern = re.compile(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*")
    raw_matches = competitor_pattern.findall(report)
    # Filter out single-word matches that look like section headers
    competitors = [
        m for m in raw_matches
        if len(m.split()) >= 2 or (len(m) > 6 and m not in {
            "Summary", "Profile", "Recommendation", "Competitor", "Executive",
            "Market", "Company", "Report", "Analysis", "Overview",
        })
    ]
    unique_competitors = set(competitors)
    competitor_count = len(unique_competitors)
    properties.append(
        QualityProperty(
            name="named_competitors",
            passed=competitor_count >= 3,
            pass_delta=2.0,
            fail_delta=2.0,
            detail=f"found {competitor_count} unique named competitors",
        )
    )

    # Numeric citations: meaningful numbers
    numeric_pattern = re.compile(r"\d+\.?\d*%?")
    numbers = numeric_pattern.findall(report)
    number_count = len(numbers)
    properties.append(
        QualityProperty(
            name="numeric_citations",
            passed=number_count >= 5,
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"found {number_count} numeric citations",
        )
    )

    # Chart validity: at least one chart exists and > 1000 bytes
    valid_charts = [
        p for p in chart_paths
        if Path(p).exists() and Path(p).stat().st_size > 1000
    ]
    properties.append(
        QualityProperty(
            name="chart_validity",
            passed=len(valid_charts) >= 1,
            pass_delta=1.0,
            fail_delta=2.0,
            detail=f"found {len(valid_charts)} valid charts",
        )
    )

    # Report structure: contains required section keywords
    lower_report = report.lower()
    has_structure = all(
        kw in lower_report
        for kw in ("summary", "profile", "recommend")
    )
    properties.append(
        QualityProperty(
            name="report_structure",
            passed=has_structure,
            pass_delta=1.0,
            fail_delta=1.0,
            detail="report contains summary/profile/recommend sections"
            if has_structure
            else "missing required section keywords",
        )
    )

    return compute_score(properties, pipeline="competitive_analysis")


def score_poster_batch(poster_path: Path) -> QualityScore:
    """Score a poster image output.

    Args:
        poster_path: Path to the generated poster image.

    Returns:
        QualityScore for this poster batch output.
    """
    from PIL import Image

    import numpy as np

    properties: list[QualityProperty] = []

    img = Image.open(poster_path)
    width, height = img.size

    # Image dimensions: exactly 800x600 (gate)
    correct_dims = width == 800 and height == 600
    properties.append(
        QualityProperty(
            name="image_dimensions",
            passed=correct_dims,
            pass_delta=0.0,
            fail_delta=0.0,
            detail=f"dimensions {width}x{height}, expected 800x600",
            is_gate=True,
        )
    )

    # Visual density: file size > 50KB
    file_size = Path(poster_path).stat().st_size
    properties.append(
        QualityProperty(
            name="visual_density",
            passed=file_size > 50_000,
            pass_delta=2.0,
            fail_delta=2.0,
            detail=f"file size {file_size} bytes",
        )
    )

    # Not monochrome: numpy std dev > 20
    arr = np.array(img)
    std_dev = float(arr.std())
    properties.append(
        QualityProperty(
            name="not_monochrome",
            passed=std_dev > 20.0,
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"pixel std dev {std_dev:.2f}",
        )
    )

    return compute_score(properties, pipeline="poster_batch")


def score_content_generate(
    content: str,
    title: str,
    pdf_path: str | Path | None = None,
    hashtags: list[str] | None = None,
) -> QualityScore:
    """Score a content generation output.

    Args:
        content: The generated text content.
        title: The title of the generated piece.
        pdf_path: Path to the rendered PDF file, or None if not rendered.
        hashtags: Optional list of hashtags included.

    Returns:
        QualityScore for this content generation output.
    """
    properties: list[QualityProperty] = []

    # Content length > 100 chars (gate)
    content_len = len(content)
    properties.append(
        QualityProperty(
            name="content_length",
            passed=content_len > 100,
            pass_delta=0.0,
            fail_delta=0.0,
            detail=f"content length {content_len} chars",
            is_gate=True,
        )
    )

    # Title quality: 0 < len < 80
    title_len = len(title)
    properties.append(
        QualityProperty(
            name="title_quality",
            passed=0 < title_len < 80,
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"title length {title_len}",
        )
    )

    # PDF renders: exists and > 5KB (skipped if no path given)
    if pdf_path is not None:
        pdf_p = Path(pdf_path)
        pdf_ok = pdf_p.exists() and pdf_p.stat().st_size > 5_000
        properties.append(
            QualityProperty(
                name="pdf_renders",
                passed=pdf_ok,
                pass_delta=1.0,
                fail_delta=2.0,
                detail=f"PDF exists={pdf_p.exists()}, "
                f"size={pdf_p.stat().st_size if pdf_p.exists() else 0}",
            )
        )

    # Has hashtags >= 3 (bonus, no penalty)
    tag_count = len(hashtags) if hashtags else 0
    properties.append(
        QualityProperty(
            name="has_hashtags",
            passed=tag_count >= 3,
            pass_delta=1.0,
            fail_delta=0.0,
            detail=f"{tag_count} hashtags provided",
        )
    )

    return compute_score(properties, pipeline="content_generate")


def score_clone_converge(
    template_path: Path,
    composite_score: float,
    iterations: int,
) -> QualityScore:
    """Score a clone-and-converge template output.

    Args:
        template_path: Path to the HTML template file.
        composite_score: Convergence score in [0, 1].
        iterations: Number of refinement iterations performed.

    Returns:
        QualityScore for this clone-converge output.
    """
    properties: list[QualityProperty] = []

    template_text = Path(template_path).read_text(encoding="utf-8")

    # Has placeholders: >= 2 {{ }} vars
    placeholder_pattern = re.compile(r"\{\{[^}]+\}\}")
    placeholders = placeholder_pattern.findall(template_text)
    properties.append(
        QualityProperty(
            name="has_placeholders",
            passed=len(placeholders) >= 2,
            pass_delta=2.0,
            fail_delta=2.0,
            detail=f"found {len(placeholders)} placeholder variables",
        )
    )

    # Valid HTML: has <html> and </html> (gate)
    has_html = "<html>" in template_text.lower() and "</html>" in template_text.lower()
    properties.append(
        QualityProperty(
            name="valid_html",
            passed=has_html,
            pass_delta=0.0,
            fail_delta=0.0,
            detail="has <html> and </html> tags" if has_html else "missing HTML tags",
            is_gate=True,
        )
    )

    # Convergence score > 0.6
    properties.append(
        QualityProperty(
            name="convergence_score",
            passed=composite_score > 0.6,
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"convergence score {composite_score:.3f}",
        )
    )

    # Multiple iterations >= 2 (bonus, no penalty)
    properties.append(
        QualityProperty(
            name="multiple_iterations",
            passed=iterations >= 2,
            pass_delta=1.0,
            fail_delta=0.0,
            detail=f"{iterations} iterations performed",
        )
    )

    return compute_score(properties, pipeline="clone_converge")


def score_tts_generate(
    file_path: Path,
    text_length: int,
) -> QualityScore:
    """Score a text-to-speech audio output.

    Args:
        file_path: Path to the generated MP3 file.
        text_length: Length of the input text in characters.

    Returns:
        QualityScore for this TTS output.
    """
    properties: list[QualityProperty] = []

    audio_path = Path(file_path)
    raw_bytes = audio_path.read_bytes()

    # MP3 header valid: ID3 or sync bytes (gate)
    has_id3 = raw_bytes[:3] == b"ID3"
    has_sync = len(raw_bytes) >= 2 and raw_bytes[0] == 0xFF and (raw_bytes[1] & 0xE0) == 0xE0
    valid_header = has_id3 or has_sync
    properties.append(
        QualityProperty(
            name="mp3_header_valid",
            passed=valid_header,
            pass_delta=0.0,
            fail_delta=0.0,
            detail="ID3 header found"
            if has_id3
            else ("sync bytes found" if has_sync else "no valid MP3 header"),
            is_gate=True,
        )
    )

    # File size > text_length * 50
    file_size = audio_path.stat().st_size
    size_ok = file_size > text_length * 50
    properties.append(
        QualityProperty(
            name="file_size_adequate",
            passed=size_ok,
            pass_delta=1.0,
            fail_delta=2.0,
            detail=f"file size {file_size}, threshold {text_length * 50}",
        )
    )

    # Duration adequate: > max(16000, (text_length / 2.5) * 16000) samples
    # We approximate duration from file size (128kbps MP3 ≈ 16000 bytes/sec)
    estimated_samples = file_size / 16_000 * 16_000  # proportional to duration
    duration_threshold = max(16_000, (text_length / 2.5) * 16_000)
    duration_ok = estimated_samples > duration_threshold
    properties.append(
        QualityProperty(
            name="duration_adequate",
            passed=duration_ok,
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"estimated samples {estimated_samples:.0f}, "
            f"threshold {duration_threshold:.0f}",
        )
    )

    return compute_score(properties, pipeline="tts_generate")
