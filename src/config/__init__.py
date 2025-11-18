"""Configuration loader backed by YAML + environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(__file__).with_name("config.yaml")
USER_CONFIG_ENV = "CODEWIKIBENCH_CONFIG"
DEFAULT_USER_CONFIG = Path.home() / ".config" / "codewikibench" / "config.yaml"


def _load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(base.get(key), dict)
        ):
            base[key] = _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _load_config() -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    if CONFIG_PATH.exists():
        config = _load_yaml(CONFIG_PATH)

    user_paths = []
    env_path = os.environ.get(USER_CONFIG_ENV)
    if env_path:
        user_paths.append(Path(env_path).expanduser())
    user_paths.append(DEFAULT_USER_CONFIG)

    for candidate in user_paths:
        if candidate and candidate.exists():
            config = _deep_update(config, _load_yaml(candidate))
            break

    return config


_CONFIG = _load_config()
_PROJECT_CFG: Dict[str, Any] = _CONFIG.get("project", {})
_LLM_CFG: Dict[str, Any] = _CONFIG.get("llm", {})

_DATA_DIR_ENV = _PROJECT_CFG.get("data_dir_env", "CODEWIKIBENCH_DATA_DIR")
_HOME_ENV = _PROJECT_CFG.get("home_env", "CODEWIKIBENCH_HOME")
_HOME_DATA_SUBDIR = _PROJECT_CFG.get("home_data_subdir", "data")
_DEFAULT_DATA_SUBDIR = _PROJECT_CFG.get("default_data_subdir", "data")

MAX_TOKENS_PER_TOOL_RESPONSE = int(
    _PROJECT_CFG.get("max_tokens_per_tool_response", 36_000)
)


def _resolve_data_dir() -> Path:
    env_dir = os.environ.get(_DATA_DIR_ENV)
    if env_dir:
        return Path(env_dir).expanduser()

    home_root = os.environ.get(_HOME_ENV)
    if home_root:
        return Path(home_root).expanduser() / _HOME_DATA_SUBDIR

    cwd_candidate = Path.cwd() / _DEFAULT_DATA_SUBDIR
    try:
        cwd_candidate.mkdir(parents=True, exist_ok=True)
        return cwd_candidate
    except OSError:
        return PROJECT_ROOT / _DEFAULT_DATA_SUBDIR


DATA_DIR = _resolve_data_dir()
SRC_DIR = PROJECT_ROOT / "src"

API_KEY = os.environ.get("API_KEY", _LLM_CFG.get("api_key", "sk-1234"))
MODEL = os.environ.get("MODEL", _LLM_CFG.get("model", "claude-sonnet-4"))
EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL", _LLM_CFG.get("embedding_model", "gemini-embedding-001")
)
BASE_URL = os.environ.get("BASE_URL", _LLM_CFG.get("base_url", "http://localhost:4000/"))


def get_project_path(*paths: str) -> str:
    return str(PROJECT_ROOT.joinpath(*paths))


def get_data_path(*paths: str) -> str:
    return str(DATA_DIR.joinpath(*paths))
