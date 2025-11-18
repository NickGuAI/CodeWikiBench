#!/usr/bin/env python3
"""
Visualization script for rubric evaluation results.

This script provides various ways to view and analyze the evaluation results:
- Overall score summary
- Detailed breakdown by category
- Low-scoring requirements that need attention
- Export to different formats
"""

import json
import argparse
import os
from pathlib import Path
from typing import Dict, List, Any
import config

def parse_args():
    parser = argparse.ArgumentParser(description="Visualize rubric evaluation results")
    parser.add_argument("--results-file", help="Absolute path to evaluation results JSON file")
    parser.add_argument("--repo-name", help="Name of the repository")
    parser.add_argument("--reference", help="Name of the folder that contains the reference documentation needed for evaluation")
    parser.add_argument("--format", choices=["summary", "detailed", "csv", "markdown"], 
                       default="summary", help="Output format")
    parser.add_argument("--min-score", type=float, default=0.0, 
                       help="Only show items with score >= this value")
    parser.add_argument("--max-score", type=float, default=1.0,
                       help="Only show items with score <= this value") 
    return parser.parse_args()

def calculate_overall_metrics(scored_rubrics: List[Dict]) -> Dict[str, float]:
    """Calculate overall metrics from scored rubrics"""
    def collect_all_items(items: List[Dict]) -> List[Dict]:
        all_items = []
        for item in items:
            all_items.append(item)
            if "sub_tasks" in item and item["sub_tasks"]:
                all_items.extend(collect_all_items(item["sub_tasks"]))
        return all_items
    
    all_items = collect_all_items(scored_rubrics)
    leaf_items = [item for item in all_items if "sub_tasks" not in item or not item["sub_tasks"]]
    
    # Overall weighted score
    total_weighted_score = sum(item["score"] * item["weight"] for item in scored_rubrics)
    total_weight = sum(item["weight"] for item in scored_rubrics)
    overall_score = total_weighted_score / total_weight if total_weight > 0 else 0
    
    # Leaf metrics
    leaf_scores = [item["score"] for item in leaf_items]
    avg_leaf_score = sum(leaf_scores) / len(leaf_scores) if leaf_scores else 0
    documented_leaves = sum(1 for score in leaf_scores if score > 0)
    coverage_percentage = (documented_leaves / len(leaf_scores)) * 100 if leaf_scores else 0
    
    return {
        "overall_score": overall_score,
        "average_leaf_score": avg_leaf_score,
        "total_requirements": len(all_items),
        "leaf_requirements": len(leaf_items),
        "documented_leaves": documented_leaves,
        "coverage_percentage": coverage_percentage
    }

def print_summary(scored_rubrics: List[Dict]):
    """Print a summary of the evaluation results"""
    metrics = calculate_overall_metrics(scored_rubrics)
    
    print("=" * 60)
    print("DOCUMENTATION EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Overall Score: {metrics['overall_score']:.4f}")
    print(f"Average Leaf Score: {metrics['average_leaf_score']:.4f}")
    print(f"Coverage: {metrics['documented_leaves']}/{metrics['leaf_requirements']} leaf requirements ({metrics['coverage_percentage']:.1f}%)")
    print(f"Total Requirements: {metrics['total_requirements']}")
    print()
    
    # Top-level category scores
    print("TOP-LEVEL CATEGORY SCORES:")
    print("-" * 40)
    for i, item in enumerate(scored_rubrics):
        print(f"{i+1}. {item['requirements'][:80]}...")
        print(f"   Score: {item['score']:.4f} | Weight: {item['weight']}")
        print()

def print_detailed(scored_rubrics: List[Dict], min_score: float = 0.0, max_score: float = 1.0):
    """Print detailed breakdown of all requirements"""
    
    def print_item(item: Dict, indent: int = 0, path: str = ""):
        score = item.get("score", 0)
        if not (min_score <= score <= max_score):
            return
            
        prefix = "  " * indent
        status = "✓" if score > 0.5 else "✗"
        
        print(f"{prefix}{status} [{score:.4f}] {item['requirements']}")
        
        # Print evaluation details for leaf nodes
        if "evaluation" in item:
            eval_data = item["evaluation"]
            print(f"{prefix}    Reasoning: {eval_data.get('reasoning', 'N/A')}")
            if eval_data.get('evidence'):
                evidence = eval_data['evidence'][:100] + "..." if len(eval_data['evidence']) > 100 else eval_data['evidence']
                print(f"{prefix}    Evidence: {evidence}")
        
        # Recurse to sub-tasks
        if "sub_tasks" in item and item["sub_tasks"]:
            for j, sub_item in enumerate(item["sub_tasks"]):
                print_item(sub_item, indent + 1, f"{path}.{j}" if path else str(j))
    
    print("=" * 60)
    print("DETAILED EVALUATION RESULTS")
    print("=" * 60)
    print(f"Showing items with score between {min_score} and {max_score}")
    print()
    
    for i, item in enumerate(scored_rubrics):
        print_item(item, 0, str(i))
        print()

def export_to_csv(scored_rubrics: List[Dict], output_file: str):
    """Export results to CSV format"""
    import csv
    
    def collect_flat_items(items: List[Dict], path: str = "") -> List[Dict]:
        flat_items = []
        for i, item in enumerate(items):
            current_path = f"{path}.{i}" if path else str(i)
            
            flat_item = {
                "path": current_path,
                "requirement": item["requirements"],
                "score": item.get("score", 0),
                "weight": item["weight"],
                "is_leaf": "sub_tasks" not in item or not item["sub_tasks"]
            }
            
            if "evaluation" in item:
                eval_data = item["evaluation"]
                flat_item.update({
                    "reasoning": eval_data.get("reasoning", ""),
                    "evidence": eval_data.get("evidence", "")
                })
            
            flat_items.append(flat_item)
            
            if "sub_tasks" in item and item["sub_tasks"]:
                flat_items.extend(collect_flat_items(item["sub_tasks"], current_path))
        
        return flat_items
    
    flat_items = collect_flat_items(scored_rubrics)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        if flat_items:
            fieldnames = flat_items[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat_items)
    
    print(f"Results exported to {output_file}")

def export_to_markdown(scored_rubrics: List[Dict], output_file: str):
    """Export results to Markdown format"""
    
    def item_to_markdown(item: Dict, level: int = 1) -> str:
        score = item.get("score", 0)
        status_emoji = "✅" if score > 0.7 else "⚠️" if score > 0.3 else "❌"
        
        md = f"{'#' * level} {status_emoji} {item['requirements']} (Score: {score:.4f})\n\n"
        
        if "evaluation" in item:
            eval_data = item["evaluation"]
            md += f"**Reasoning:** {eval_data.get('reasoning', 'N/A')}\n\n"
            if eval_data.get('evidence'):
                md += f"**Evidence:** {eval_data['evidence']}\n\n"
        
        if "sub_tasks" in item and item["sub_tasks"]:
            for sub_item in item["sub_tasks"]:
                md += item_to_markdown(sub_item, level + 1)
        
        return md
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# Documentation Evaluation Results\n\n")
        
        metrics = calculate_overall_metrics(scored_rubrics)
        f.write(f"**Overall Score:** {metrics['overall_score']:.4f}\n")
        f.write(f"**Coverage:** {metrics['coverage_percentage']:.1f}%\n")
        f.write(f"**Total Requirements:** {metrics['total_requirements']}\n\n")
        
        for item in scored_rubrics:
            f.write(item_to_markdown(item))
    
    print(f"Results exported to {output_file}")

def visualize_results(
    results_file: str | None = None,
    repo_name: str | None = None,
    reference: str | None = None,
    output_format: str = "summary",
    min_score: float = 0.0,
    max_score: float = 1.0,
):
    """Render evaluation results to stdout/files."""
    if not results_file:
        if not repo_name:
            print("Error: Either --results-file or --repo-name must be provided")
            return None
        if not reference:
            print("Reference docs not specified, attempting to auto-detect...")
            preferred = ["codewiki", "deepwiki", "original"]
            detected_reference = None
            data_dir = Path(config.get_data_path(repo_name))
            for candidate in preferred:
                docs_tree = data_dir / candidate / "docs_tree.json"
                if docs_tree.exists():
                    detected_reference = candidate
                    print(f"Detected reference docs: {candidate}")
                    break
            if not detected_reference:
                candidates = [d for d in data_dir.iterdir() if d.is_dir() and (d / "docs_tree.json").exists()]
                if candidates:
                    detected_reference = candidates[0].name
                    print(f"Using first available reference docs: {detected_reference}")
            reference = detected_reference

        if not reference:
            print("Unable to locate reference docs automatically.")
            return None

        default_path = Path(config.get_data_path(repo_name, reference, "evaluation_results"))
        results_file = os.path.join(default_path, "combined_evaluation_results.json")
        if not os.path.exists(results_file):
            individual_files = [
                f for f in os.listdir(default_path) if f.endswith(".json") and not f.startswith("combined")
            ]
            if len(individual_files) == 1:
                results_file = os.path.join(default_path, individual_files[0])
                print(f"Combined results not found, using individual results: {individual_files[0]}")
            elif len(individual_files) > 1:
                print(f"Multiple individual result files found: {individual_files}")
                print("Please specify --results-file or run combination step first")
                return None
            else:
                print(f"No evaluation result files found in {default_path}")
                return None

    with open(results_file, "r") as f:
        data = json.load(f)

    if isinstance(data, dict) and "rubrics" in data:
        scored_rubrics = data["rubrics"]
        metadata = data.get("combination_metadata", {})
        print(f"Using combined results from {metadata.get('num_evaluations_combined', 'unknown')} evaluations")
        print(f"Combination method: {metadata.get('combination_method', 'unknown')}")
        print()
    elif isinstance(data, list):
        scored_rubrics = data
    else:
        print(f"Error: Unexpected JSON structure in {results_file}")
        return None

    if output_format == "summary":
        print_summary(scored_rubrics)
    elif output_format == "detailed":
        print_detailed(scored_rubrics, min_score, max_score)
    elif output_format == "csv":
        export_to_csv(scored_rubrics, results_file.replace(".json", ".csv"))
    elif output_format == "markdown":
        export_to_markdown(scored_rubrics, results_file.replace(".json", ".md"))

    return results_file


def main():
    args = parse_args()
    visualize_results(
        results_file=args.results_file,
        repo_name=args.repo_name,
        reference=args.reference,
        output_format=args.format,
        min_score=args.min_score,
        max_score=args.max_score,
    )

if __name__ == "__main__":
    main() 
