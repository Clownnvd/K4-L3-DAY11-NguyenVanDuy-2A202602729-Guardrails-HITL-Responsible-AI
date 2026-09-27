#!/usr/bin/env python3
"""
Machine-readable grader for Assignment 11 packaging + public tests.

Usage:
  python scripts/grade.py --submission-dir . --out outputs/grade_report.json

Exit codes:
  0 = ran successfully (see report for scores / technical_failure)
  2 = could not start grading (missing paths)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None


def validate_schema(submission: Path) -> dict:
    results = submission / "outputs" / "results.json"
    schema = submission / "schemas" / "results.schema.json"
    if not schema.exists():
        # allow schema from this tooling repo when grading an external zip layout
        schema = Path(__file__).resolve().parents[1] / "schemas" / "results.schema.json"
    if not results.exists():
        return {"ok": False, "error": "missing outputs/results.json", "points": 0}
    if jsonschema is None:
        return {"ok": False, "error": "jsonschema not installed", "points": 0}
    try:
        data = json.loads(results.read_text(encoding="utf-8"))
        sch = json.loads(schema.read_text(encoding="utf-8"))
        jsonschema.validate(instance=data, schema=sch)
        return {"ok": True, "error": None, "points": 10, "student_id": data.get("student_id")}
    except Exception as e:
        return {"ok": False, "error": str(e), "points": 0}


def required_files(submission: Path) -> dict:
    checks = {
        "audit": (submission / "outputs" / "audit_log.json").exists(),
        "metrics": (submission / "outputs" / "metrics.json").exists(),
        "results": (submission / "outputs" / "results.json").exists(),
        "attack_results": (submission / "outputs" / "attack_results.json").exists(),
    }
    # Core bắt buộc: results + attack_results. audit/metrics khuyến nghị.
    ok = checks["results"] and checks["attack_results"]
    return {
        "ok": ok,
        "details": {k: bool(v) for k, v in checks.items()},
        "required": ["results", "attack_results"],
        "recommended": ["audit", "metrics"],
    }


def run_pytest(submission: Path, path: str) -> dict:
    cmd = [sys.executable, "-m", "pytest", path, "-q", "--tb=no"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(submission),
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-2000:],
            "technical_failure": proc.returncode == 2,
        }
    except Exception as e:
        return {
            "returncode": 2,
            "stdout": "",
            "stderr": str(e),
            "technical_failure": True,
        }


def main():
    parser = argparse.ArgumentParser(description="Grade Assignment 11 submission package")
    parser.add_argument("--submission-dir", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, default=Path("outputs/grade_report.json"))
    parser.add_argument("--skip-public-tests", action="store_true")
    args = parser.parse_args()

    root = args.submission_dir.resolve()
    if not root.exists():
        print(f"Submission dir not found: {root}", file=sys.stderr)
        sys.exit(2)

    files = required_files(root)
    schema = validate_schema(root)

    public = {"skipped": True}
    if not args.skip_public_tests:
        public = run_pytest(root, "tests/public")

    # Machine portion is packaging (files+schema) only here; rubric points for
    # pipeline behavior come from public/hidden pytest + human review.
    technical_failure = (not files["ok"]) or (not schema["ok"]) or public.get("technical_failure", False)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "submission_dir": str(root),
        "technical_failure": technical_failure,
        "packaging": files,
        "results_schema": schema,
        "public_tests": public,
        "human_review_required": [
            "red_team_prompt_quality",
            "unsafe_leak_default_model",
            "bonus_b1_hard_model_unsafe_leak",
            "bonus_b2_guards_leak_replay",
        ],
        "bonus_rubric": {
            "B1_hard_model": {
                "points": 5,
                "models": ["gemini-3.8-flash", "gpt-5.6-luna"],
                "requires": "unsafe leaked=true + grader replay + llm_model matches",
            },
            "B2_guards_leak": {
                "points_per_leak": 2,
                "max_points": 10,
                "requires": "guards leaked=true + grader replay",
            },
            "max_bonus_total": 15,
        },
        "notes": (
            "Packaging + schema + public tests. "
            "Base 100: CP2 40 + CP3 40 + CP4 20. "
            "Bonus max +15: B1 hard-model unsafe leak +5; "
            "B2 guards leak +2 each (max +10). "
            "JSON is evidence only — replay decides bonus."
        ),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    attack_path = root / "outputs" / "attack_results.json"
    attack_summary = {}
    if attack_path.exists():
        try:
            attack_summary = json.loads(attack_path.read_text(encoding="utf-8")).get("summary", {})
        except (OSError, json.JSONDecodeError):
            attack_summary = {}

    lab_report = args.out.parent / "lab_report.md"
    lab_report.write_text(
        "\n".join([
            "# Day 11 — Báo cáo tự kiểm",
            "",
            f"- Lỗi kỹ thuật: `{'Có' if technical_failure else 'Không'}`",
            f"- Đóng gói đủ artifact bắt buộc: `{'Có' if files['ok'] else 'Không'}`",
            f"- `results.json` đúng schema: `{'Có' if schema['ok'] else 'Không'}`",
            f"- Public tests return code: `{public.get('returncode', 'skipped')}`",
            f"- Unsafe leaked: `{attack_summary.get('unsafe_leaked', 'chưa chạy')}`",
            f"- Guards leaked: `{attack_summary.get('guards_leaked', 'chưa chạy')}`",
            "",
            "Điểm bonus chỉ được xác nhận sau khi grader replay prompt trên đúng model.",
            "",
        ]),
        encoding="utf-8",
    )
    print(json.dumps({
        "out": str(args.out),
        "lab_report": str(lab_report),
        "technical_failure": technical_failure,
    }, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
