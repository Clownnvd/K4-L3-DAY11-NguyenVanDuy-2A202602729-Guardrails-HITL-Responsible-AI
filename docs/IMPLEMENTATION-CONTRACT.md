# Implementation contract — Day 11 Guardrails

## User-visible outcome

The local VinBank lab must provide a deterministic defense-in-depth pipeline, generate the artifacts required by the grader, and include a full-width visual runner that explains each decision as a request moves through the pipeline.

## In scope

- Input injection detection with Unicode canonicalization and banking topic filtering.
- Output redaction for lab secrets and common Vietnamese PII.
- Per-user sliding-window rate limiting.
- Audit records, monitoring counters, alerts, and exact-host egress policy.
- Generated `outputs/results.json`, `audit_log.json`, and `metrics.json`.
- Five advanced red-team prompts and the starter's generated attack artifacts.
- A static visual runner for safe, attack, rate-limit, and output-redaction scenarios.

## Excluded from required grading scope

- Optional NeMo Guardrails and LLM-as-Judge implementation.
- Claiming bonus points without a live model replay.
- Publishing or submitting the repository.

## Invariants

- Safe banking requests are not blocked.
- Injection and off-topic requests stop before the model.
- Secret or PII text cannot leave the output or egress boundary unchanged.
- Egress requires HTTPS and an exact allowlisted VinBank host.
- Required artifacts are produced by code, never hand-authored.
- The interface never signals state with color alone and honors reduced motion.

## Acceptance checks

1. `pytest tests/smoke -q` passes.
2. `pytest tests/public -q` passes after artifacts are generated.
3. `pytest tests/test_assignment_behaviors.py -q` passes.
4. `python src/main.py --part 2` prints successful guardrail checks without an API call.
5. `python src/main.py --part 5` generates schema-valid defense artifacts.
6. `python scripts/grade.py --submission-dir . --out outputs/grade_report.json` reports no technical failure once attack artifacts exist.
7. The visual runner works at 390, 768, 1440, and 1920 px; keyboard focus and reduced-motion behavior are verified in a real browser.
