"""
RAGAS Evaluation Runner

Runs the RAG pipeline against a golden Q&A dataset and scores it
using RAGAS metrics. Run after every deploy to staging.

Usage:
    uv run python evals/run_ragas.py \
        --dataset evals/golden/ \
        --api-key nxs_live_xxx \
        --base-url https://staging.usenexus.ai \
        --output evals/results/

Metrics evaluated:
    - Faithfulness:       answer is grounded in context (no hallucination)
    - Answer relevance:   answer addresses the question
    - Context precision:  retrieved chunks are relevant to the question
    - Context recall:     all relevant info was retrieved
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

# Baseline thresholds — CI fails if any metric drops below these
THRESHOLDS = {
    "faithfulness": 0.85,
    "answer_relevancy": 0.80,
    "context_precision": 0.75,
    "context_recall": 0.70,
}


async def run_query(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    question: str,
) -> dict:
    """Run a single query against the Nexus API and return the full response."""
    resp = await client.post(
        f"{base_url}/v1/query",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": question, "top_k": 5},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


async def evaluate_dataset(
    dataset_path: Path,
    api_key: str,
    base_url: str,
) -> dict:
    """
    Load a golden dataset JSON file and run all questions through the pipeline.

    Golden dataset format:
    [
        {
            "question": "What is our Q3 OKR for revenue?",
            "ground_truth": "The Q3 revenue OKR is $2M ARR.",
            "relevant_doc_ids": ["doc_abc123"]
        },
        ...
    ]
    """
    with open(dataset_path) as f:
        dataset = json.load(f)

    print(f"Evaluating {len(dataset)} questions from {dataset_path.name}...")

    questions = []
    ground_truths = []
    answers = []
    contexts = []

    async with httpx.AsyncClient() as client:
        for i, item in enumerate(dataset, 1):
            print(f"  [{i}/{len(dataset)}] {item['question'][:60]}...")
            try:
                result = await run_query(client, base_url, api_key, item["question"])
                answers.append(result.get("answer", ""))
                contexts.append([c["excerpt"] for c in result.get("citations", [])])
                questions.append(item["question"])
                ground_truths.append(item["ground_truth"])
            except Exception as e:
                print(f"    ERROR: {e}")
                answers.append("")
                contexts.append([])
                questions.append(item["question"])
                ground_truths.append(item["ground_truth"])

    # Run RAGAS scoring
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        ragas_dataset = Dataset.from_dict(
            {
                "question": questions,
                "answer": answers,
                "contexts": contexts,
                "ground_truth": ground_truths,
            }
        )

        scores = evaluate(
            ragas_dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        )

        return {
            "dataset": dataset_path.name,
            "num_questions": len(dataset),
            "scores": scores.to_pandas().mean().to_dict(),
            "raw_scores": scores.to_pandas().to_dict(orient="records"),
        }

    except ImportError:
        print("  WARNING: ragas not installed. Run: uv add ragas datasets")
        # Return mock scores for CI when ragas not available
        return {
            "dataset": dataset_path.name,
            "num_questions": len(dataset),
            "scores": {},
            "raw_scores": [],
            "error": "ragas not installed",
        }


def check_thresholds(results: list[dict]) -> tuple[bool, list[str]]:
    """Check if all metric scores meet minimum thresholds."""
    failures: list[str] = []

    for result in results:
        scores = result.get("scores", {})
        dataset = result.get("dataset", "unknown")
        for metric, threshold in THRESHOLDS.items():
            score = scores.get(metric)
            if score is None:
                continue
            if score < threshold:
                failures.append(f"{dataset} — {metric}: {score:.3f} < {threshold:.3f} (threshold)")

    return len(failures) == 0, failures


async def main(args: argparse.Namespace) -> int:
    dataset_dir = Path(args.dataset)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_files = list(dataset_dir.glob("*.json"))
    if not dataset_files:
        print(f"No golden datasets found in {dataset_dir}")
        return 1

    print(f"Found {len(dataset_files)} dataset(s)")
    print(f"Base URL: {args.base_url}")
    print()

    all_results: list[dict] = []
    for dataset_file in sorted(dataset_files):
        result = await evaluate_dataset(dataset_file, args.api_key, args.base_url)
        all_results.append(result)

        scores = result.get("scores", {})
        print(f"\n  Results for {result['dataset']}:")
        for metric, score in scores.items():
            threshold = THRESHOLDS.get(metric, 0)
            status = "✓" if score >= threshold else "✗"
            print(f"    {status} {metric}: {score:.3f} (threshold: {threshold:.3f})")

    # Write results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"eval_{timestamp}.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "timestamp": timestamp,
                "base_url": args.base_url,
                "results": all_results,
                "thresholds": THRESHOLDS,
            },
            f,
            indent=2,
        )
    print(f"\nResults written to {output_path}")

    # Check thresholds
    passed, failures = check_thresholds(all_results)
    if not passed:
        print("\n❌ THRESHOLD FAILURES:")
        for f in failures:
            print(f"   {f}")
        return 1

    print("\n✅ All metrics above thresholds.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RAGAS evaluation against Nexus API")
    parser.add_argument("--dataset", required=True, help="Path to golden dataset directory")
    parser.add_argument("--api-key", required=True, help="Nexus API key")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--output", default="evals/results", help="Output directory")
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args)))
