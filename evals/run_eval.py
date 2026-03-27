from __future__ import annotations

from pathlib import Path
import sys

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.hybrid_tool import answer_question


def load_benchmark_questions() -> list[dict]:
    benchmark_path = Path(__file__).with_name("benchmark_questions.yaml")
    return yaml.safe_load(benchmark_path.read_text(encoding="utf-8"))


def run_routing_eval() -> dict:
    cases = load_benchmark_questions()
    results = []
    correct = 0

    for case in cases:
        response = answer_question(case["question"])
        matched = response["route"] == case["expected_route"]
        correct += int(matched)
        results.append(
            {
                "question": case["question"],
                "expected_route": case["expected_route"],
                "predicted_route": response["route"],
                "matched": matched,
            }
        )

    total = len(results)
    accuracy = correct / total if total else 0.0
    return {"routing_accuracy": accuracy, "cases": results}


if __name__ == "__main__":
    summary = run_routing_eval()
    print(f"Routing accuracy: {summary['routing_accuracy']:.2%}")
    for case in summary["cases"]:
        print(f"- {case['predicted_route']:>6} | expected={case['expected_route']:<6} | matched={case['matched']} | {case['question']}")
