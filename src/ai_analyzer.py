from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal
from urllib import error, request

from src.diff_engine import DiffRegion


Severity = Literal["low", "medium", "high"]
Category = Literal[
    "layout",
    "styling",
    "content",
    "missing-element",
    "extra-element",
    "state-change",
    "other",
]


@dataclass(frozen=True)
class RegionContext:
    index: int
    x: int
    y: int
    width: int
    height: int
    area: float


@dataclass(frozen=True)
class BugFinding:
    title: str
    summary: str
    severity: Severity
    category: Category
    region_index: int
    evidence: str


@dataclass(frozen=True)
class BugReport:
    summary: str
    confidence: float
    needs_human_review: bool
    findings: List[BugFinding]


@dataclass(frozen=True)
class OllamaConfig:
    model: str = "llava"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.0
    timeout_seconds: int = 120
    max_regions: int = 10


BUG_REPORT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_human_review": {"type": "boolean"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "layout",
                            "styling",
                            "content",
                            "missing-element",
                            "extra-element",
                            "state-change",
                            "other",
                        ],
                    },
                    "region_index": {"type": "integer", "minimum": 0},
                    "evidence": {"type": "string"},
                },
                "required": [
                    "title",
                    "summary",
                    "severity",
                    "category",
                    "region_index",
                    "evidence",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "confidence", "needs_human_review", "findings"],
    "additionalProperties": False,
}


class AIAnalyzerError(RuntimeError):
    pass


class OllamaVisionAnalyzer:
    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config or OllamaConfig()

    def analyze(
        self,
        baseline_path: Path,
        current_path: Path,
        diff_regions: List[DiffRegion],
    ) -> BugReport:
        baseline_image = _encode_image(baseline_path)
        current_image = _encode_image(current_path)
        region_context = _build_region_context(diff_regions, self.config.max_regions)

        prompt = _build_prompt(region_context)
        payload = {
            "model": self.config.model,
            "stream": False,
            "format": BUG_REPORT_SCHEMA,
            "options": {
                "temperature": self.config.temperature,
            },
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a visual QA assistant. Compare the baseline UI screenshot "
                        "against the current screenshot. Focus on the supplied diff regions, "
                        "ignore harmless rendering noise, and return only valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                    "images": [baseline_image, current_image],
                },
            ],
        }

        response_json = self._post_chat(payload)
        content = response_json.get("message", {}).get("content", "")
        if not content:
            raise AIAnalyzerError("Ollama returned an empty response.")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIAnalyzerError(f"Ollama returned invalid JSON: {exc}") from exc

        return _parse_bug_report(parsed)

    def _post_chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        endpoint = f"{self.config.base_url.rstrip('/')}/api/chat"
        http_request = request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise AIAnalyzerError(
                "Failed to connect to Ollama. Make sure Ollama is running and the model is available."
            ) from exc
        except json.JSONDecodeError as exc:
            raise AIAnalyzerError("Ollama returned a malformed HTTP response.") from exc


def analyze_visual_bug(
    baseline_path: Path,
    current_path: Path,
    diff_regions: List[DiffRegion],
    config: OllamaConfig | None = None,
) -> BugReport:
    analyzer = OllamaVisionAnalyzer(config=config)
    return analyzer.analyze(
        baseline_path=baseline_path,
        current_path=current_path,
        diff_regions=diff_regions,
    )


def bug_report_to_json(report: BugReport) -> str:
    return json.dumps(asdict(report), indent=2)


def _encode_image(image_path: Path) -> str:
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def _build_region_context(diff_regions: List[DiffRegion], max_regions: int) -> List[RegionContext]:
    region_context: List[RegionContext] = []

    for index, region in enumerate(diff_regions[:max_regions]):
        region_context.append(
            RegionContext(
                index=index,
                x=region.x,
                y=region.y,
                width=region.width,
                height=region.height,
                area=region.area,
            )
        )

    return region_context


def _build_prompt(region_context: List[RegionContext]) -> str:
    regions_json = json.dumps([asdict(region) for region in region_context], indent=2)
    schema_json = json.dumps(BUG_REPORT_SCHEMA, indent=2)

    return f"""
You will receive two images in this order:
1. Baseline screenshot
2. Current screenshot

Your job:
- Compare the current screenshot against the baseline.
- Focus on meaningful UI regressions only.
- Use the provided diff regions as guidance, not as proof.
- Ignore tiny anti-aliasing shifts, compression artifacts, and harmless color noise.
- If the evidence is weak, set needs_human_review to true.

Diff regions:
{regions_json}

Return JSON that matches this schema exactly:
{schema_json}
""".strip()


def _parse_bug_report(payload: Dict[str, Any]) -> BugReport:
    summary = _require_type(payload, "summary", str)
    confidence = _require_number(payload, "confidence")
    needs_human_review = _require_type(payload, "needs_human_review", bool)
    findings_payload = _require_type(payload, "findings", list)

    findings: List[BugFinding] = []
    for item in findings_payload:
        if not isinstance(item, dict):
            raise AIAnalyzerError("Each finding must be an object.")

        findings.append(
            BugFinding(
                title=_require_type(item, "title", str),
                summary=_require_type(item, "summary", str),
                severity=_require_literal(
                    item,
                    "severity",
                    {"low", "medium", "high"},
                ),
                category=_require_literal(
                    item,
                    "category",
                    {
                        "layout",
                        "styling",
                        "content",
                        "missing-element",
                        "extra-element",
                        "state-change",
                        "other",
                    },
                ),
                region_index=int(_require_number(item, "region_index", allow_float=False)),
                evidence=_require_type(item, "evidence", str),
            )
        )

    return BugReport(
        summary=summary,
        confidence=confidence,
        needs_human_review=needs_human_review,
        findings=findings,
    )


def _require_type(payload: Dict[str, Any], field_name: str, expected_type: type) -> Any:
    value = payload.get(field_name)
    if not isinstance(value, expected_type):
        raise AIAnalyzerError(f"Field '{field_name}' must be of type {expected_type.__name__}.")
    return value


def _require_number(
    payload: Dict[str, Any],
    field_name: str,
    allow_float: bool = True,
) -> float:
    value = payload.get(field_name)
    valid_types = (int, float) if allow_float else (int,)
    if isinstance(value, bool) or not isinstance(value, valid_types):
        type_name = "number" if allow_float else "integer"
        raise AIAnalyzerError(f"Field '{field_name}' must be a {type_name}.")
    return float(value)


def _require_literal(payload: Dict[str, Any], field_name: str, allowed_values: set[str]) -> str:
    value = _require_type(payload, field_name, str)
    if value not in allowed_values:
        raise AIAnalyzerError(
            f"Field '{field_name}' must be one of: {', '.join(sorted(allowed_values))}."
        )
    return value
