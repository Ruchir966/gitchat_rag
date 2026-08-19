"""
RAGAS Evaluation Script for GitChat RAG
========================================

Runs your RAG pipeline against a test dataset and scores it using RAGAS metrics:
  • Faithfulness     — Is the answer grounded in the retrieved context?
  • Answer Relevancy — Does the answer address the question?
  • Context Precision — Are the relevant chunks ranked higher?
  • Context Recall    — Did retrieval capture all needed info?

Usage:
  cd ai-service
  python -m src.eval.run_eval                      # Default: test_dataset.json
  python -m src.eval.run_eval --dataset custom.json # Custom dataset
  python -m src.eval.run_eval --verbose             # Print per-question details
"""

import json
import os
import sys
import argparse
import time
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from datasets import Dataset
from ragas import evaluate
from ragas.metrics.collections import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
)
from ragas.llms import llm_factory
from ragas.embeddings import HuggingFaceEmbeddings
from openai import OpenAI as OpenAIClient

# Import your own RAG pipeline
from src.agent import run_agent, get_vectorstore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EVAL_DIR = Path(__file__).parent
DEFAULT_DATASET = EVAL_DIR / "test_dataset.json"
RESULTS_DIR = EVAL_DIR / "results"


def load_test_dataset(path: str) -> list[dict]:
    """Load and validate the test dataset JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    required_keys = {"question", "ground_truth", "repo_url"}
    for i, item in enumerate(data):
        missing = required_keys - set(item.keys())
        if missing:
            raise ValueError(f"Dataset item {i} is missing keys: {missing}")
        if item["repo_url"].startswith("REPLACE"):
            raise ValueError(
                f"Dataset item {i}: replace 'repo_url' with your actual ingested repo URL.\n"
                f"  Open {path} and update all 'repo_url' fields."
            )
    return data


def run_pipeline_for_eval(question: str, repo_url: str) -> dict:
    """
    Run the RAG pipeline and return the data RAGAS needs:
      - answer (str)
      - contexts (list[str])
    """
    result = run_agent(question=question, repo_url=repo_url, chat_history=[])

    # Re-run retrieval to capture the actual context chunks for RAGAS.
    # Try with repo_url pre_filter first; fall back to unfiltered search if the
    # Atlas index doesn't have metadata.repo_url declared as a filter field.
    vectorstore = get_vectorstore()
    contexts = []

    # Attempt 1: filtered by repo_url (requires Atlas index filter field)
    try:
        docs_with_scores = vectorstore.similarity_search_with_score(
            query=question,
            k=12,
            pre_filter={"metadata.repo_url": {"$eq": repo_url}},
        )
        contexts = [doc.page_content for doc, score in docs_with_scores]
    except Exception:
        pass

    # Attempt 2: no pre_filter — works even without Atlas filter index config
    if not contexts:
        try:
            docs_with_scores = vectorstore.similarity_search_with_score(
                query=question, k=12
            )
            contexts = [doc.page_content for doc, score in docs_with_scores]
        except Exception:
            retriever = vectorstore.as_retriever(search_kwargs={"k": 12})
            docs = retriever.invoke(question)
            contexts = [doc.page_content for doc in docs]

    return {
        "answer": result["generation"],
        "contexts": contexts,
        "sources": result["sources"],
        "retry_count": result["retry_count"],
    }


def print_banner(text: str):
    width = 60
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def print_score_bar(label: str, score: float, width: int = 30):
    """Print a visual score bar like: Faithfulness     ████████████░░░░ 0.78"""
    filled = int(score * width)
    bar = "█" * filled + "░" * (width - filled)
    color = "\033[92m" if score >= 0.7 else "\033[93m" if score >= 0.4 else "\033[91m"
    reset = "\033[0m"
    print(f"  {label:<22} {color}{bar}{reset}  {score:.4f}")


# ---------------------------------------------------------------------------
# Main evaluation logic
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="RAGAS Evaluation for GitChat RAG")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(DEFAULT_DATASET),
        help="Path to test dataset JSON file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-question results",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to save results JSON (default: eval/results/<timestamp>.json)",
    )
    args = parser.parse_args()

    # --- Load dataset ---
    print_banner("Loading Test Dataset")
    test_data = load_test_dataset(args.dataset)
    print(f"  Loaded {len(test_data)} test questions from {args.dataset}")

    # --- Run pipeline on each question ---
    print_banner("Running RAG Pipeline")
    questions = []
    answers = []
    contexts = []
    ground_truths = []
    metadata_records = []  # Extra info per question for the report

    for i, item in enumerate(test_data):
        q = item["question"]
        repo_url = item["repo_url"]
        gt = item["ground_truth"]

        print(f"\n  [{i+1}/{len(test_data)}] {q[:80]}...")
        if i > 0:
            print("           (Waiting 15s to respect Groq free-tier rate limits...)")
            time.sleep(15)
        
        start = time.time()

        try:
            result = run_pipeline_for_eval(q, repo_url)
            elapsed = time.time() - start

            questions.append(q)
            answers.append(result["answer"])
            contexts.append(result["contexts"])
            ground_truths.append(gt)
            metadata_records.append({
                "question": q,
                "sources": result["sources"],
                "retry_count": result["retry_count"],
                "latency_seconds": round(elapsed, 2),
                "num_contexts": len(result["contexts"]),
            })

            print(f"           [OK] Done in {elapsed:.1f}s | {len(result['contexts'])} chunks | "
                  f"retries: {result['retry_count']} | sources: {result['sources']}")

        except Exception as e:
            print(f"           [FAIL] {e}")
            # Still include it with empty data so the report shows the failure
            questions.append(q)
            answers.append(f"[ERROR] {e}")
            contexts.append([""])
            ground_truths.append(gt)
            metadata_records.append({
                "question": q,
                "error": str(e),
            })

    # --- Build RAGAS dataset ---
    print_banner("Running RAGAS Evaluation")
    print("  Preparing dataset for RAGAS...")

    ragas_dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })

    # --- Configure evaluator LLM via Groq's OpenAI-compatible endpoint ---
    # RAGAS 0.4.x collections metrics require llm_factory (InstructorLLM), NOT LangchainLLMWrapper.
    # Groq exposes an OpenAI-compatible REST API, so we can point the OpenAI client at Groq.
    groq_openai_client = OpenAIClient(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    evaluator_llm = llm_factory(
        model="llama-3.1-8b-instant",
        client=groq_openai_client,
    )

    # HuggingFace embeddings (local, no API key needed) — used by AnswerRelevancy
    evaluator_embeddings = HuggingFaceEmbeddings(
        model="sentence-transformers/all-MiniLM-L6-v2"
    )

    # --- Instantiate RAGAS metrics with the evaluator LLM ---
    metrics = [
        Faithfulness(llm=evaluator_llm),
        AnswerRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings),
        ContextPrecision(llm=evaluator_llm),
        ContextRecall(llm=evaluator_llm),
    ]

    print("  Evaluating with RAGAS (this may take a few minutes)...\n")

    try:
        result = evaluate(
            dataset=ragas_dataset,
            metrics=metrics,
        )
    except Exception as e:
        print(f"\n  [ERROR] RAGAS evaluation failed: {e}")
        print("  This can happen if the Groq rate limit is hit during evaluation.")
        print("  Try again in a minute, or reduce the dataset size.")
        sys.exit(1)

    # --- Display results ---
    print_banner("RAGAS Evaluation Results")

    scores = {
        "Faithfulness": result["faithfulness"],
        "Answer Relevancy": result["answer_relevancy"],
        "Context Precision": result["context_precision"],
        "Context Recall": result["context_recall"],
    }

    for label, score in scores.items():
        print_score_bar(label, score)

    # Overall score (average)
    avg_score = sum(scores.values()) / len(scores)
    print()
    print_score_bar("OVERALL (avg)", avg_score)

    # --- Interpretation ---
    print_banner("Score Interpretation")
    for label, score in scores.items():
        if score >= 0.8:
            verdict = "[EXCELLENT]"
        elif score >= 0.6:
            verdict = "[ACCEPTABLE] room for improvement"
        elif score >= 0.4:
            verdict = "[NEEDS WORK]"
        else:
            verdict = "[POOR] investigate this metric"
        print(f"  {label:<22} {score:.4f}  ->  {verdict}")

    # --- Verbose: per-question breakdown ---
    if args.verbose:
        print_banner("Per-Question Details")
        df = result.to_pandas()
        for idx, row in df.iterrows():
            print(f"\n  ── Q{idx+1}: {row['question'][:70]}...")
            print(f"     Faithfulness:      {row.get('faithfulness', 'N/A')}")
            print(f"     Answer Relevancy:  {row.get('answer_relevancy', 'N/A')}")
            print(f"     Context Precision: {row.get('context_precision', 'N/A')}")
            print(f"     Context Recall:    {row.get('context_recall', 'N/A')}")
            meta = metadata_records[idx] if idx < len(metadata_records) else {}
            if meta.get("retry_count", 0) > 0:
                print(f"     [!] Retries: {meta['retry_count']}")
            if meta.get("latency_seconds"):
                print(f"     Latency: {meta['latency_seconds']}s")

    # --- Save results ---
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = args.output or str(RESULTS_DIR / f"eval_{timestamp}.json")

    report = {
        "timestamp": timestamp,
        "dataset_path": args.dataset,
        "num_questions": len(questions),
        "aggregate_scores": scores,
        "overall_average": round(avg_score, 4),
        "per_question_metadata": metadata_records,
        "per_question_scores": result.to_pandas().to_dict(orient="records"),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n  [REPORT] Full report saved to: {output_path}")
    print()


if __name__ == "__main__":
    main()
