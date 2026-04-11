from __future__ import annotations

from pathlib import Path

from src.ai_analyzer import OllamaConfig, analyze_visual_bug, bug_report_to_json
from src.diff_engine import run_diff


def run_pipeline(test_name: str = "login_test") -> str:
    result = run_diff(test_name)

    base_dir = Path(__file__).resolve().parent
    test_dir = base_dir / "data" / "screenshots" / test_name
    report = analyze_visual_bug(
        baseline_path=test_dir / "baseline.png",
        current_path=test_dir / "current.png",
        diff_regions=result.regions,
        config=OllamaConfig(),
    )

    report_json = bug_report_to_json(report)
    report_path = test_dir / "report.json"
    report_path.write_text(report_json + "\n", encoding="utf-8")

    print(report_json)
    print(f"[SUCCESS] Report saved to {report_path}")
    return report_json


if __name__ == "__main__":
    run_pipeline()
