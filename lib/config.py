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
# In dev mode config.py lives inside lib/; look one level up if needed.
_CONFIG_PATH = _REPO_ROOT / "workflow_config.yaml"
if not _CONFIG_PATH.is_file():
    _CONFIG_PATH = _REPO_ROOT.parent / "workflow_config.yaml"

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
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
    }

    if not _CONFIG_PATH.is_file():
        _CONFIG_CACHE = default
        return _CONFIG_CACHE

    try:
        data = yaml_utils.load_yaml(str(_CONFIG_PATH)) or {}
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
        _CONFIG_CACHE = default

    return _CONFIG_CACHE


def get_llm_config() -> Dict[str, Any]:
    """
    Return LLM-related configuration.

    Keys:
        backend:  "cline" or "openai" (default: "cline")
        base_url: base URL for the OpenAI-compatible API (default: https://api.openai.com/v1)
        model:    model name to use (default: gpt-4o-mini)
    """
    return _load_raw_config().get("llm", {})


def get_output_config() -> Dict[str, Any]:
    """
    Return output-related configuration.

    Keys:
        versioned: bool — if True, create numbered dirs (out/<name>-2/, etc.)
                          if False, overwrite the same dir each run (default: True)
    """
    return _load_raw_config().get("output", {})

