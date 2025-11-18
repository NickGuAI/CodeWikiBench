## Setup

### Install the CLI (pipx or pip)
```bash
pipx install .             # installs the console script globally
# or: pip install .        # installs into the active environment

codebenchmark --help
```

By default the CLI writes datasets under `./data` (relative to wherever you run it). Override this by setting
`CODEWIKIBENCH_DATA_DIR=/absolute/path` or `CODEWIKIBENCH_HOME=/absolute/path` (the latter appends `/data` automatically) before invoking `codebenchmark`.
For global config (LLM base URL, models, etc.), create `~/.config/codewikibench/config.yaml` or set
`export CODEWIKIBENCH_CONFIG=/path/to/custom.yaml`; those values override the packaged defaults without reinstalling.

### Run GPT-OSS locally with Ollama
Follow the [OpenAI Cookbook guide](https://cookbook.openai.com/articles/gpt-oss/run-locally-ollama) to prepare GPT-OSS so `codebenchmark rubrics --model gpt-oss:20b` can navigate docs with tools:

1. [Install Ollama](https://ollama.com) and make sure the daemon is running.
2. Pull the GPT-OSS checkpoints you plan to use (the 20B build works on ≥16 GB unified memory; the 120B build needs ≥60 GB):
   ```bash
   ollama pull gpt-oss:20b
   # or: ollama pull gpt-oss:120b
   ```
3. Point CodeWikiBench at the local Ollama API (the defaults match the cookbook, but you can override them via env vars):
   ```bash
   export BASE_URL=${BASE_URL:-http://localhost:11434/v1}
   export API_KEY=${API_KEY:-ollama}   # Ollama ignores the key but the client requires one
   ```
4. Generate rubrics with GPT-OSS while keeping doc-navigation tools enabled:
   ```bash
   codebenchmark rubrics --adapter deepwiki --repo electron --model gpt-oss:20b --use-tools
   ```

### Local development (uv)
We still use [uv](https://github.com/astral-sh/uv) for day-to-day development:

```bash
uv sync
uv run codebenchmark --help
```

The rest of this guide assumes you have the CLI on your `PATH` (e.g., via `pipx install .`). Replace `codebenchmark ...` with `uv run codebenchmark ...` if you prefer not to install it.

## Documentation Inputs
CodeWikiBench accepts any documentation source that has been parsed into `structured_docs.json` + `docs_tree.json` under `data/<repo>/<folder>/`. Two common flows are DeepWiki crawls and CodeWiki exports.

### DeepWiki
Crawl DeepWiki docs ([example result](examples/electron/deepwiki/docs))
```bash
codebenchmark download \
  --adapter deepwiki \
  --repo electron \
  --url https://deepwiki.com/electron/electron
```

Parse the downloaded DeepWiki docs ([example result](examples/electron/deepwiki))
```bash
codebenchmark parse --adapter deepwiki --repo electron
```

### CodeWiki
Parse CodeWiki docs ([example result](examples/electron/codewiki))
```bash
codebenchmark parse \
  --adapter codewiki \
  --repo electron \
  --input-dir /home/anhnh/CodeWiki/output/docs/All-Hands-AI--electron \
  --output-dir data/electron/codewiki
```

> Each parsed folder can be named however you like (`deepwiki`, `codewiki`, `team-notes`, ...). Both pipelines auto-detect the first folder that contains `docs_tree.json`, and you can override their choice with `--docs-source <folder>` (rubrics) or `--reference <folder>` (evaluation) whenever needed.

## Rubrics Generation
Generate rubrics with multiple models
```bash
codebenchmark rubrics --adapter deepwiki --repo electron --models claude-sonnet-4,kimi-k2-instruct --visualize

# Use docs parsed into a different folder under data/<repo>
codebenchmark rubrics --adapter codewiki --repo electron --model kimi-k2-instruct
```

## Evaluation
### Complete Evaluation Pipeline
Run evaluation with multiple models
```bash
codebenchmark eval --adapter deepwiki --repo electron --models kimi-k2-instruct --visualize --batch-size 8
codebenchmark eval --adapter deepwiki --repo electron --models kimi-k2-instruct,gpt-oss-120b,gemini-2.5-flash --visualize --batch-size 4

# Point at a different parsed folder
codebenchmark eval --adapter codewiki --repo electron --models kimi-k2-instruct --batch-size 4
```


### Visualize Results
```bash
# Using the complete pipeline (recommended) – already handled by `codebenchmark eval --visualize`

# Manual visualization of specific results
# Summary view
python judge/visualize_evaluation.py --repo-name electron --reference deepwiki --format summary

# Detailed view with all requirements  
python judge/visualize_evaluation.py --repo-name electron --reference deepwiki --format detailed

# Show only poorly documented requirements (score < 0.5)
python judge/visualize_evaluation.py --repo-name electron --reference deepwiki --format detailed --max-score 0.5

# Export to CSV for analysis
python judge/visualize_evaluation.py --repo-name electron --reference deepwiki --format csv

# Export to Markdown report
python judge/visualize_evaluation.py --repo-name electron --reference deepwiki --format markdown
```

## Lines of Code
```bash
# Count lines in the main branch (use the latest commit ID)
python3 count_lines_of_code.py https://github.com/All-Hands-AI/electron.git HEAD

# Count lines at a specific commit
python3 count_lines_of_code.py https://github.com/All-Hands-AI/electron.git a1b2c3d4e5f6

# Show detailed file-by-file breakdown
python3 count_lines_of_code.py https://github.com/All-Hands-AI/electron.git 30604c40fc6e9ac914089376f41e118582954f22
```
