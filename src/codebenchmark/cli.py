import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, List, Optional

import click

import config
from docs_parser.crawl_deepwiki_docs import download_deepwiki_docs
from docs_parser.parse_generated_docs import SUPPORTED_ADAPTERS, parse_docs
from rubrics_generator.generate_rubrics import detect_docs_source as detect_rubrics_docs, run as run_rubrics_generation
from rubrics_generator.combine_rubrics import combine_rubrics_for_repo
from rubrics_generator.visualize_rubrics import visualize_rubrics
from judge.judge import detect_docs_source as detect_reference_docs, run as run_evaluations
from judge.combine_evaluations import combine_evaluations_for_repo
from judge.visualize_evaluation import visualize_results

DEFAULT_RUBRICS_MODELS = ["claude-sonnet-4", "kimi-k2-instruct", "glm-4p5"]
DEFAULT_EVAL_MODELS = ["gpt4.1-mini", "kimi-k2-instruct", "glm-4p5"]


def _data_path(*parts: str) -> Path:
    return Path(config.get_data_path(*parts))


def _sanitize_model_name(model: str) -> str:
    return model.replace("/", "_")


def _parse_model_list(
    models: Optional[str],
    single_model: Optional[str],
    default: Iterable[str],
) -> List[str]:
    value = models or single_model
    if not value:
        return list(default)
    parsed = [m.strip() for m in value.split(",") if m.strip()]
    if not parsed:
        raise click.ClickException("No valid models provided.")
    return parsed


def _parse_weights(weights: Optional[str]) -> Optional[List[float]]:
    if not weights:
        return None
    try:
        return [float(w.strip()) for w in weights.split(",") if w.strip()]
    except ValueError as exc:
        raise click.ClickException(f"Invalid weights list '{weights}': {exc}") from exc


def _resolve_docs_source(repo_name: str, adapter: Optional[str], detector) -> str:
    base_path = _data_path(repo_name)
    if adapter:
        candidate = base_path / adapter
        docs_tree = candidate / "docs_tree.json"
        if docs_tree.exists():
            return adapter
        raise click.ClickException(
            f"Could not find parsed docs for adapter '{adapter}' under {candidate}. "
            "Run the parse step first or choose a different adapter."
        )
    return detector(str(base_path))


def _run_async(coro):
    return asyncio.run(coro)


@click.group()
def app():
    """Unified CLI for downloading, parsing, and benchmarking documentation."""


@app.command()
@click.option("--adapter", default="deepwiki", show_default=True, help="Documentation adapter to use.")
@click.option("--url", required=True, help="Source URL for downloads (adapter specific).")
@click.option("--output-dir", help="Directory to store downloaded docs (defaults to data/<repo>/<adapter>/docs).")
@click.option("--repo", "repo_name", help="Repository name to infer default paths.")
def download(adapter: str, url: str, output_dir: Optional[str], repo_name: Optional[str]):
    """Download documentation for a repo (currently only DeepWiki is supported)."""
    adapter = adapter.lower()
    if adapter != "deepwiki":
        raise click.ClickException(f"Adapter '{adapter}' is not supported for downloads.")

    if not output_dir:
        if not repo_name:
            raise click.ClickException("Either provide --output-dir or supply --repo to infer the destination.")
        output_dir = str(_data_path(repo_name, adapter, "docs"))

    click.echo(f"Downloading {adapter} docs from {url} to {output_dir}")
    download_deepwiki_docs(url, output_dir)
    click.echo("Download completed.")


@app.command()
@click.option("--adapter", default="deepwiki", show_default=True, help="Documentation adapter (deepwiki/codewiki).")
@click.option("--repo", "repo_name", required=True, help="Repository name (used for data/<repo>/...).")
@click.option("--input-dir", help="Directory containing adapter output (defaults to data/<repo>/<adapter>/docs).")
@click.option("--output-dir", help="Where parsed docs should be written (defaults to data/<repo>/<adapter>).")
def parse(adapter: str, repo_name: str, input_dir: Optional[str], output_dir: Optional[str]):
    """Parse downloaded docs into structured JSON trees."""
    adapter_normalized = adapter.lower()
    if adapter_normalized not in SUPPORTED_ADAPTERS:
        raise click.ClickException(
            f"Adapter '{adapter}' is not supported. Choose from: {', '.join(sorted(SUPPORTED_ADAPTERS))}."
        )

    input_path = Path(input_dir) if input_dir else _data_path(repo_name, adapter_normalized, "docs")
    if not input_path.exists():
        raise click.ClickException(f"Input directory not found: {input_path}")

    output_path = Path(output_dir) if output_dir else _data_path(repo_name, adapter_normalized)
    click.echo(f"Parsing {adapter_normalized} docs from {input_path} -> {output_path}")
    parse_docs(adapter_normalized, repo_name, str(input_path), str(output_path))
    click.echo(f"Structured docs written to {output_path}")


@app.command()
@click.option("--adapter", help="Parsed docs folder under data/<repo> (auto-detected when omitted).")
@click.option("--repo", "repo_name", required=True, help="Repository name under data/.")
@click.option("--models", default=None, help="Comma separated list of models.")
@click.option("--model", "single_model", default=None, help="Single model alias for --models.")
@click.option("--use-tools/--no-use-tools", default=True, show_default=True, help="Toggle doc navigation tools.")
@click.option("--visualize", is_flag=True, default=False, help="Visualize combined rubrics after generation.")
@click.option("--temperature", default=0.1, show_default=True, help="Temperature for combination step.")
@click.option("--max-retries", default=3, show_default=True, help="Max retries for rubric combination.")
def rubrics(
    adapter: Optional[str],
    repo_name: str,
    models: Optional[str],
    single_model: Optional[str],
    use_tools: bool,
    visualize: bool,
    temperature: float,
    max_retries: int,
):
    """Generate rubrics from parsed docs and combine them."""
    docs_source = _resolve_docs_source(repo_name, adapter, detect_rubrics_docs)
    model_list = _parse_model_list(models, single_model, DEFAULT_RUBRICS_MODELS)

    click.echo(f"Using docs source '{docs_source}' for repo '{repo_name}'.")
    for model in model_list:
        click.echo(f"Generating rubrics with {model}...")
        args = SimpleNamespace(
            repo_name=repo_name,
            use_tools=use_tools,
            model=model,
            docs_source=docs_source,
        )
        _run_async(run_rubrics_generation(args))

    click.echo("Combining rubrics...")
    combined_path = _run_async(
        combine_rubrics_for_repo(
            repo_name=repo_name,
            temperature=temperature,
            max_retries=max_retries,
        )
    )

    if visualize and combined_path:
        click.echo(f"Visualizing {combined_path}")
        visualize_rubrics(str(combined_path))


@app.command(name="eval")
@click.option("--adapter", help="Reference docs folder under data/<repo> (auto-detected when omitted).")
@click.option("--repo", "repo_name", required=True, help="Repository name under data/.")
@click.option("--models", default=None, help="Comma separated list of models to evaluate.")
@click.option("--model", "single_model", default=None, help="Single model alias for --models.")
@click.option("--batch-size", default=5, show_default=True, help="Batch size for evaluation.")
@click.option("--max-retries", default=2, show_default=True, help="Max retries for evaluation errors.")
@click.option(
    "--combination-method",
    type=click.Choice(["average", "majority_vote", "weighted_average", "max", "min"]),
    default="average",
    show_default=True,
    help="How to combine evaluation results.",
)
@click.option("--weights", help="Comma separated weights for weighted_average.")
@click.option("--use-tools/--no-use-tools", default=True, show_default=True, help="Toggle doc navigation tools.")
@click.option("--enable-retry/--disable-retry", default=False, show_default=True, help="Enable evaluation retries.")
@click.option("--visualize", is_flag=True, default=False, help="Visualize evaluation output.")
def evaluate(
    adapter: Optional[str],
    repo_name: str,
    models: Optional[str],
    single_model: Optional[str],
    batch_size: int,
    max_retries: int,
    combination_method: str,
    weights: Optional[str],
    use_tools: bool,
    enable_retry: bool,
    visualize: bool,
):
    """Run evaluation pipeline for generated rubrics."""
    reference = _resolve_docs_source(repo_name, adapter, detect_reference_docs)
    model_list = _parse_model_list(models, single_model, DEFAULT_EVAL_MODELS)
    click.echo(f"Evaluating docs '{reference}' for repo '{repo_name}' with models: {', '.join(model_list)}")

    result_paths: List[Path] = []
    for model in model_list:
        click.echo(f"Evaluating with {model}...")
        args = SimpleNamespace(
            repo_name=repo_name,
            reference=reference,
            use_tools=use_tools,
            model=model,
            rubrics_file=None,
            batch_size=batch_size,
            enable_retry=enable_retry,
            max_retries=max_retries,
        )
        _run_async(run_evaluations(args))
        result_paths.append(_data_path(repo_name, reference, "evaluation_results", f"{_sanitize_model_name(model)}.json"))

    combined_path = None
    if len(model_list) > 1:
        click.echo("Combining evaluation results...")
        combined_path = combine_evaluations_for_repo(
            repo_name=repo_name,
            reference=reference,
            method=combination_method,
            weights=_parse_weights(weights),
        )
    else:
        combined_path = str(result_paths[0])

    if visualize and combined_path:
        visualize_results(results_file=combined_path, repo_name=repo_name, reference=reference)
