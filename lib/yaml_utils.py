"""
yaml_utils.py — Shared YAML helpers built on top of PyYAML.

Provides small, focused helpers so callers never talk to PyYAML directly.
This makes it easy to swap implementations later if needed.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict

try:
    import yaml
except ImportError as exc:  # pragma: no cover - import error surfaced at runtime
    raise ImportError(
        "PyYAML is required but not installed. Install with `pip install PyYAML`."
    ) from exc


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def load_yaml(path: str) -> Any:
    """
    Load a YAML file from disk using yaml.safe_load.

    Args:
        path: Absolute or relative path to a .yml/.yaml file.

    Returns:
        Parsed Python object (dict, list, scalar, or None).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the YAML cannot be parsed.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"YAML file not found: {path}")

    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:  # pragma: no cover - surface with context
        raise ValueError(f"Failed to parse YAML file: {path}") from exc


def load_yaml_frontmatter(md_path: str) -> Dict[str, Any]:
    """
    Extract and parse YAML frontmatter from a Markdown file.

    Expects a leading block of the form:

        ---
        key: value
        ---

    Returns:
        Dict obtained by yaml.safe_load of the frontmatter block.

    Raises:
        FileNotFoundError: If the Markdown file does not exist.
        ValueError: If no frontmatter is found or the parsed value is not a dict.
    """
    if not os.path.isfile(md_path):
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    m = _FRONTMATTER_RE.match(content)
    if not m:
        raise ValueError(f"No YAML frontmatter found in {md_path}")

    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:  # pragma: no cover
        raise ValueError(f"Failed to parse YAML frontmatter in {md_path}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected YAML frontmatter in {md_path} to be a mapping, "
            f"got {type(data).__name__}"
        )

    return data


def write_yaml(path: str, data: Any) -> None:
    """
    Write a Python object to a YAML file with stable, readable formatting.

    This is optional for callers that want a standardized YAML writer.
    """
    dirname = os.path.dirname(path)
    if dirname and not os.path.isdir(dirname):
        os.makedirs(dirname, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

