"""
Lab 11 — Main Entry Point

Core: Checkpoint 2 (guardrails) → 3 (suite) → 4 (attacks)
Optional: --part 3 / --part 4

Usage:
    python main.py              # Core: parts 2, 5, 1
    python main.py --part 2     # Checkpoint 2
    python main.py --part 5     # Checkpoint 3
    python main.py --part 1     # Checkpoint 4
"""
import sys
import asyncio
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from core.config import setup_api_key


async def part1_attacks():
    """Checkpoint 4: attack unsafe agent, then guards agent (điểm cộng)."""
    print("\n" + "=" * 60)
    print("CHECKPOINT 4: Attack Unsafe + Guards agents")
    print("=" * 60)

    from agents.agent import create_unsafe_agent, test_agent
    from agents.guards_agent import create_guards_agent
    from attacks.attacks import run_attacks, save_attack_results

    unsafe_agent, unsafe_runner = create_unsafe_agent()
    await test_agent(unsafe_agent, unsafe_runner)

    print("\n--- Attacks on UNSAFE agent ---")
    unsafe_results = await run_attacks(
        unsafe_agent, unsafe_runner, target_name="unsafe"
    )

    print("\n--- Attacks on GUARDS agent (điểm cộng nếu LEAKED) ---")
    guards_agent, guards_runner = create_guards_agent()
    guards_results = await run_attacks(
        guards_agent, guards_runner, target_name="guards"
    )

    save_attack_results(
        unsafe_results=unsafe_results,
        guards_results=guards_results,
        ai_attacks=None,
    )

    bonus_leaks = sum(1 for r in guards_results if r.get("leaked"))
    print("\n" + "=" * 60)
    print(f"Guards leaks (bonus B2): {bonus_leaks}  → +2/leak max +10 sau khi grader replay")
    from core.config import is_harder_model, provider_label

    if is_harder_model():
        print(
            f"Hard model ({provider_label()}): "
            "unsafe leak → bonus B1 +5 nếu grader replay OK"
        )
    print("=" * 60)

    return {
        "unsafe": unsafe_results,
        "guards": guards_results,
    }


async def part2_guardrails():
    """Checkpoint 2: input + output guardrails."""
    print("\n" + "=" * 60)
    print("CHECKPOINT 2: Guardrails")
    print("=" * 60)

    print("\n--- Input Guardrails ---")
    from guardrails.input_guardrails import (
        test_injection_detection,
        test_topic_filter,
        test_input_plugin,
    )
    test_injection_detection()
    print()
    test_topic_filter()
    print()
    await test_input_plugin()

    print("\n--- Output Guardrails ---")
    from guardrails.output_guardrails import test_content_filter
    test_content_filter()
    print("(LLM-as-Judge / NeMo — optional, skipped)")


async def part3_testing():
    """Optional enrichment (không chấm)."""
    print("\n" + "=" * 60)
    print("OPTIONAL: Security Testing Pipeline (không chấm)")
    print("=" * 60)

    from testing.testing import run_comparison, print_comparison, SecurityTestPipeline
    from agents.agent import create_unsafe_agent

    print("\n--- Before/After Comparison ---")
    unprotected, protected = await run_comparison()
    if unprotected and protected:
        print_comparison(unprotected, protected)
    else:
        print("Optional — chưa implement, bỏ qua.")

    print("\n--- Security Test Pipeline ---")
    agent, runner = create_unsafe_agent()
    pipeline = SecurityTestPipeline(agent, runner)
    results = await pipeline.run_all()
    if results:
        pipeline.print_report(results)
    else:
        print("Optional — chưa implement, bỏ qua.")


def part4_hitl():
    """Optional enrichment (không chấm — HITL nằm trong report CP5)."""
    print("\n" + "=" * 60)
    print("OPTIONAL: HITL code (không chấm)")
    print("=" * 60)
    print("Optional enrichment — không chấm.\n")

    from hitl.hitl import test_confidence_router, test_hitl_points

    print("\n--- Confidence Router ---")
    test_confidence_router()

    print("\n--- HITL Decision Points ---")
    test_hitl_points()


async def part5_assignment_suite():
    """Checkpoint 3: defense suite → outputs/results.json."""
    import os

    print("\n" + "=" * 60)
    print("CHECKPOINT 3: Assignment suite → outputs/*.json")
    print("=" * 60)

    from assignment.pipeline import (
        build_production_plugins,
        build_observability,
        run_assignment_suite,
    )

    student_id = os.environ.get("STUDENT_ID", "").strip() or "SE00000"
    try:
        plugins = build_production_plugins(use_llm_judge=False)
        audit, monitor = build_observability()
        pipeline = {"plugins": plugins, "audit": audit, "monitor": monitor}
        result = await run_assignment_suite(pipeline, student_id=student_id)
        print("Suite finished.")
        print(f"Wrote outputs under repo outputs/ (student_id={student_id})")
        return result
    except NotImplementedError as e:
        print(
            "Chưa xong Checkpoint 3 (src/assignment/pipeline.py). "
            "Hoàn thành rồi chạy lại:\n"
            "  cd src\n"
            "  python main.py --part 5"
        )
        print(f"Detail: {e}")
        return None


async def main(parts=None):
    setup_api_key()

    if parts is None:
        parts = [2, 5, 1]  # CP2 → CP3 → CP4

    for part in parts:
        if part == 1:
            await part1_attacks()
        elif part == 2:
            await part2_guardrails()
        elif part == 3:
            await part3_testing()
        elif part == 4:
            part4_hitl()
        elif part == 5:
            await part5_assignment_suite()
        else:
            print(f"Unknown part: {part}")

    print("\n" + "=" * 60)
    print("Lab 11 complete! Check your results above.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Lab 11: Guardrails / HITL / Red Team — theo Checkpoint 1–5"
    )
    parser.add_argument(
        "--part",
        type=int,
        choices=[1, 2, 3, 4, 5],
        help="2=CP2 guardrails, 5=CP3 suite, 1=CP4 attacks, 3/4=optional",
    )
    args = parser.parse_args()

    if args.part:
        asyncio.run(main(parts=[args.part]))
    else:
        asyncio.run(main())
