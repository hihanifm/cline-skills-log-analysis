"""
config.py — Central configuration loader for workflows and LLM settings.

Reads workflow_config.yaml from the repo root (alongside setup.py) and exposes
typed helpers so individual scripts don't need to know about file layout.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml_utils


_REPO_ROOT = Path(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = _REPO_ROOT / "workflow_config.yaml"

_CONFIG_CACHE: Dict[str, Any] | None = None


def _load_raw_config() -> Dict[str, Any]:
    """
    Load workflow_config.yaml once and cache it.
    Falls back to built-in defaults if the file is missing or invalid.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    default: Dict[str, Any] = {
        "llm": {
            "backend": "cline",
            "api_key_env": "ANTHROPIC_API_KEY",
        },
        "output": {
            "base_dir_env": "WORKFLOW_OUTPUT_DIR",
            "default_base": "./workflow-output",
        },
    }

    if not _CONFIG_PATH.is_file():
        _CONFIG_CACHE = default
        return _CONFIG_CACHE

    try:
        data = yaml_utils.load_yaml(str(_CONFIG_PATH)) or {}
        # Shallow merge with defaults so missing sections/keys are filled in.
        cfg = default.copy()
        for key, val in data.items():
            if isinstance(val, dict) and isinstance(cfg.get(key), dict):
                merged = cfg[key].copy()
                merged.update(val)
                cfg[key] = merged
            else:
                cfg[key] = val
        _CONFIG_CACHE = cfg
    except Exception:
        # On any parse error, fall back to safe defaults.
        _CONFIG_CACHE = default

    return _CONFIG_CACHE


def get_llm_config() -> Dict[str, Any]:
    """
    Return LLM-related configuration.

    Keys:
        backend:     "cline" or "anthropic" (default: "cline")
        api_key_env: name of env var holding the Anthropic API key
    """
    cfg = _load_raw_config()
    return cfg.get("llm", {})


def get_output_config() -> Dict[str, Any]:
    """
    Return workflow output configuration.

    Keys:
        base_dir_env: name of env var used as a global override for base dir
        default_base: default base dir (string path, usually relative to repo root)
    """
    cfg = _load_raw_config()
    return cfg.get("output", {})


def resolve_output_base(default_base: Path) -> Path:
    """
    Resolve the effective base directory for workflow outputs, combining:

    - config.output.base_dir_env (env var override, if set)
    - config.output.default_base (relative to repo root)
    - provided default_base (typically the input directory) as final fallback.
    """
    out_cfg = get_output_config()
    base_var = out_cfg.get("base_dir_env", "WORKFLOW_OUTPUT_DIR")
    cfg_default = out_cfg.get("default_base", "./workflow-output")

    env_val = os.environ.get(base_var)
    if env_val:
        return Path(env_val).expanduser()

    if cfg_default:
        cfg_path = Path(cfg_default)
        if not cfg_path.is_absolute():
            cfg_path = _REPO_ROOT / cfg_path
        return cfg_path

    return default_base

