import json
import asyncio
import argparse
import os
from pathlib import Path
from typing import Any, Dict, List

from pydantic_ai import Agent

from llm_proxy import (
    get_llm,
    is_gpt_oss_model,
    run_chat_with_tools,
    truncate_tokens,
)
import config
from tools import AgentDeps, docs_navigator_tool
from rubrics_generator.visualize_rubrics import visualize_rubrics


def detect_docs_source(base_path: str) -> str:
    preferred = ["codewiki", "deepwiki", "original"]
    for candidate in preferred:
        docs_tree = os.path.join(base_path, candidate, "docs_tree.json")
        if os.path.isfile(docs_tree):
            return candidate

    if os.path.isdir(base_path):
        for name in sorted(os.listdir(base_path)):
            candidate_path = os.path.join(base_path, name)
            docs_tree = os.path.join(candidate_path, "docs_tree.json")
            if os.path.isdir(candidate_path) and os.path.isfile(docs_tree):
                return name

    raise FileNotFoundError(
        f"No parsed documentation (docs_tree.json) found under {base_path}. "
        "Parse docs or provide --docs-source explicitly."
    )

def parse_args():
    parser = argparse.ArgumentParser(description="Generate hierarchical rubrics from documentation")
    parser.add_argument("--repo-name", required=True, help="Name of the repository")
    parser.add_argument("--use-tools", action="store_true", help="Enable tools for document navigation")
    parser.add_argument("--model", help="Model to use (default: claude-3-5-haiku-20241022 for anthropic, deepseek-r1-0528 for fireworks, gemini-2.0-flash for google)")
    parser.add_argument("--docs-source", default=None, help="Name of the parsed docs folder under data/<repo> (auto-detected when omitted)")

    return parser.parse_args()



# --- Agent ---
SYSTEM_PROMPT = """
You are a helpful assistant tasked with analyzing the official documentation of a software repository. You will be given a documentation tree and access to individual documentation files. The documentation outlines the core features and purpose of the repository, though some sections may contain redundant or non-essential information — ignore these.

<REQUIREMENTS>
Your goal is to construct a **hierarchical rubrics** of the repository. This rubrics should:

- Start from abstract, high-level rubrics and progressively drill down into more specific subrubrics.
- Cover all major functionalities and architectural constructs.
- Be structured to help users clearly understand how the repository is organized and how its components systematically work together.

Each rubric must include:
- A **descriptive name**
- A **clear explanation** of its purpose
- A **weight** representing its importance:
  - **3**: Essential
  - **2**: Important but not essential
  - **1**: Supportive or minor
- A list of **reference paths** to the documentation that supports the rubric (only required for **leaf rubrics**).

Use the following JSON format to represent the rubrics:
```json
[
  {
    "name": "Rubric 1",
    "description": "High-level purpose of Rubric 1",
    "reference": [],
    "weight": 3,
    "children": [
      {
        "name": "Rubric 1.1",
        "description": "Specific functionality under Rubric 1",
        "reference": [],
        "weight": 2,
        "children": [
          {
            "name": "Rubric 1.1.1",
            "description": "Leaf-level functionality",
            "weight": 3,
            "reference": ["ref_path_1", "ref_path_2"]
          }
        ]
      },
      {
        "name": "Rubric 1.2",
        "description": "Another function under Rubric 1",
        "weight": 1,
        "reference": ["ref_path_3"]
      }
    ]
  },
  {
    "name": "Rubric 2",
    "description": "High-level purpose of Rubric 2",
    "weight": 2,
    "reference": [],
    "children": [
      {
        "name": "Rubric 2.1",
        "description": "Functionality under Rubric 2",
        "weight": 2,
        "reference": ["ref_path_4"]
      }
    ]
  }
]
```

</REQUIREMENTS>

<GUIDELINES>
- Prioritize accessing documentation files that are **critical for understanding** the system's structure and behavior.
- Build the rubrics **iteratively**, updating and refining it as more information is gathered.
</GUIDELINES>

<TOOLS>
- You have access to a `docs_navigator` tool that retrieves real documentation snippets. Each call accepts a JSON array of navigation paths (e.g., `["subpages", 0, "content", "Overview"]`).
- **Never** emit placeholders like "TODO" or invent facts. If information is missing, pause and call `docs_navigator` again until you gather the necessary evidence.
- Cite the sections you inspected in the rubric references to prove coverage.
</TOOLS>
""".strip()

SYSTEM_PROMPT_WO_TOOLS = """
You are a skilled technical assistant assigned to analyze the official documentation of a software repository.
You will be provided with a documentation tree written primarily in a **HOW-TO-USE** format, which focuses on how to operate the repository's features and tools.
Your task is to **reverse-engineer and reconstruct the internal structure and logic of the system** by transforming this HOW-TO-USE information into a **HOW-DOES-IT-WORK** perspective.

# OBJECTIVE
Develop a **hierarchical rubric** that captures the underlying architecture and working principles of the repository. This rubric should reflect **what the system does and how its parts interact**, abstracting away from usage instructions into architectural insight.

# DELIVERABLE FORMAT
Return the rubrics in the following **nested JSON format**, where:
- Each rubric item includes a `"requirements"` field summarizing the system concept or functionality.
- Each item is assigned a `"weight"` to indicate its importance:
  - **3** = Essential to the system's core functionality
  - **2** = Important but not core
  - **1** = Minor or supporting functionality
- Items can recursively contain `"sub_tasks"` that break down more specific elements.

```json
[
  {
    "requirements": "Top-level concept or component",
    "weight": 3,
    "sub_tasks": [
      {
        "requirements": "More specific concept or subcomponent",
        "weight": 2,
        "sub_tasks": [
          {
            "requirements": "Detailed technical element or behavior",
            "weight": 3,
            "sub_tasks": [
              {
                "requirements": "Leaf-level functionality",
                "weight": 3
              },
              {
                "requirements": "More specific concept or subcomponent",
                "weight": 3,
                "sub_tasks": [
                  {
                    "requirements": "Leaf-level functionality",
                    "weight": 3,
                    "sub_tasks": [...] # dive deeper into the functionality
                  }
                ]
              }
            ]
          }
        ]
      },
      {
        "requirements": "Alternative aspect or feature",
        "weight": 1
      }
    ]
  }
]
```

# REQUIREMENTS
- Begin with **abstract, high-level components**, then drill down to concrete sub-elements.
- Structure the rubric to support **deep understanding** of the system's architecture and internal logic.
- If needed, refine the rubric **iteratively** as more parts of the documentation are reviewed.

# NOTES
- Be analytical: DO NOT mimic the documentation structure. Instead, distill and reframe it.
- Treat the documentation as evidence from which you infer **the design intent and system structure**.
""".strip()

# --- GPT-OSS helpers ---

def _docs_navigator_tool_definition() -> List[Dict[str, Any]]:
    """Return the tool schema exposed to GPT-OSS when running locally."""
    return [
        {
            "type": "function",
            "function": {
                "name": "docs_navigator",
                "description": (
                    "Look up content from structured_docs.json using JSON-style navigation paths. "
                    "Each path is a list of keys/indices such as ['subpages', 0, 'content', 'Overview']."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "minItems": 1,
                            "description": "Collection of navigation paths to inspect.",
                            "items": {
                                "type": "array",
                                "items": {
                                    "anyOf": [{"type": "string"}, {"type": "integer"}]
                                },
                                "description": "Path describing where to fetch content.",
                            },
                        }
                    },
                    "required": ["paths"],
                },
            },
        }
    ]


def _format_docs_navigator_output(paths: List[List[Any]], deps: AgentDeps) -> str:
    """Mirror the existing docs_navigator tool output and keep it token-limited."""
    chunks: List[str] = []
    for path in paths:
        if not isinstance(path, list):
            raise ValueError("Each entry in 'paths' must be a list that represents the navigation path.")
        result = deps.docs_navigator.get_content(path)
        content = json.dumps(result.get("content"), indent=2)
        chunk = [
            "--------------------------------",
            f"Path: {path}",
            f"Content: \n{content}",
        ]
        if result.get("error"):
            chunk.append(f"Error: {result['error']}")
        chunk.append("--------------------------------")
        chunks.append("\n".join(chunk))

    return truncate_tokens("\n".join(chunks))


async def _run_gpt_oss_with_tools(
    *,
    model: str,
    prompt: str,
    system_prompt: str,
    deps: AgentDeps,
) -> str:
    """Execute the cookbook tool loop manually for GPT-OSS models hosted in Ollama."""

    async def handle_tool_call(tool_call: Dict[str, Any]) -> str:
        function = tool_call.get("function", {})
        name = function.get("name")
        if name != "docs_navigator":
            return f"Unsupported tool '{name}'"
        arguments_raw = function.get("arguments") or "{}"
        try:
            arguments = json.loads(arguments_raw)
        except json.JSONDecodeError as exc:
            return f"Invalid JSON passed to docs_navigator: {exc}"

        paths = arguments.get("paths")
        if not isinstance(paths, list):
            return "docs_navigator requires a 'paths' array."
        try:
            print(f"[docs_navigator] Fetching paths: {paths}")
            return _format_docs_navigator_output(paths, deps)
        except ValueError as exc:
            return str(exc)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    return await run_chat_with_tools(
        model=model,
        messages=messages,
        tools=_docs_navigator_tool_definition(),
        handle_tool_call=handle_tool_call,
    )

# --- Run ---
async def run(args):
    # Setup paths automatically from repo name
    base_path = config.get_data_path(args.repo_name)
    docs_source = args.docs_source or detect_docs_source(base_path)
    docs_path = os.path.join(base_path, docs_source)
    docs_tree_path = os.path.join(docs_path, "docs_tree.json")
    if not os.path.exists(docs_tree_path):
        raise FileNotFoundError(
            f"docs_tree.json not found at {docs_tree_path}. "
            "Did you parse documentation into that folder or pass the correct --docs-source?"
        )
    output_dir = os.path.join(base_path, "rubrics")
    sanitized_model = args.model.replace("/", "_") if args.model else "default"
    model_name = args.model or config.MODEL

    print(f"Using documentation source: {docs_source}")

    #check if output file already exists
    if os.path.exists(os.path.join(output_dir, f"{sanitized_model}.json")):
        print(f"Rubrics already generated for {args.model}")
        return
    
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Load docs tree
    with open(docs_tree_path, "r") as f:
        docs_tree = json.load(f)

    prompt = f"""
Given the docs tree:
\"\"\"
{json.dumps(docs_tree, indent=2)}
\"\"\"

Use the docs_navigator tool to inspect any sections you need. Each path must be a JSON array of keys/indices (for example: ["subpages", 0, "content", "Overview"]). Do **not** produce placeholder text; keep calling docs_navigator until you have enough evidence to write complete rubrics that cite specific documentation paths.
""".strip()
    
    
    # Setup tools and agent
    if args.use_tools:
        system_prompt = SYSTEM_PROMPT
    else:
        system_prompt = SYSTEM_PROMPT_WO_TOOLS
    
    deps = AgentDeps(docs_path)

    if args.use_tools and is_gpt_oss_model(model_name):
        final_output = await _run_gpt_oss_with_tools(
            model=model_name,
            prompt=prompt,
            system_prompt=system_prompt,
            deps=deps,
        )
    else:
        tools = [docs_navigator_tool] if args.use_tools else []
        agent = Agent(
            model=get_llm(model_name),
            deps_type=AgentDeps,
            system_prompt=system_prompt,
            tools=tools,
        )

        agent_output = await agent.run(prompt, deps=deps)
        final_output = agent_output.output
    
    # Parse and save rubrics
    try:
        # Extract JSON from the final output
        json_start = final_output.find('[')
        json_end = final_output.rfind(']') + 1
        
        if json_start != -1 and json_end > json_start:
            rubrics_json = final_output[json_start:json_end]
            rubrics = json.loads(rubrics_json)
            
            # Save rubrics to file
            rubrics_file = os.path.join(output_dir, f"{sanitized_model}.json")
            with open(rubrics_file, "w") as f:
                json.dump(rubrics, f, indent=2)
            
            print(f"Rubrics saved to: {rubrics_file}")
            # visualize rubrics
            visualize_rubrics(rubrics_file)
        else:
            print("No valid JSON rubrics found in output")
            # Save raw output for debugging
            raw_output_file = os.path.join(output_dir, f"{sanitized_model}_raw_output.txt")
            with open(raw_output_file, "w") as f:
                f.write(final_output)
            print(f"Raw output saved to: {raw_output_file}")
            
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        # Save raw output for debugging
        raw_output_file = os.path.join(output_dir, f"{sanitized_model}_raw_output.txt")
        with open(raw_output_file, "w") as f:
            f.write(final_output)
        print(f"Raw output saved to: {raw_output_file}")

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args))
