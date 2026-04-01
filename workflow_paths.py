from __future__ import annotations

import os
from pathlib import Path


def _normalize_subdir(md_subdir: str) -> str:
    """
    Normalize markdown-defined subdirectory to be safely relative.

    - Treat empty/None as "output".
    - Strip leading path separators so it cannot escape the base.
    - Collapse "." segments via Path().as_posix().
    """
    if not md_subdir:
        return "output"

    # Ensure relative
    stripped = md_subdir.lstrip("/\\")
    # Normalize "." and redundant separators without allowing ".." traversal to escape
    norm = Path(stripped)
    # Do not resolve() here to avoid following symlinks or touching filesystem
    return norm.as_posix()


def resolve_output_dir(
    md_subdir: str,
    *,
    env_var: str = "WORKFLOW_OUTPUT_DIR",
    default_base: Path | None = None,
) -> Path:
    """
    Resolve the effective output directory for a workflow.

    Resolution rules:
    - If `env_var` is set in the environment, use it as the base directory.
    - Otherwise, fall back to `default_base` if provided.
    - The markdown-defined `md_subdir` is always treated as a relative subdirectory
      under the chosen base.
    """
    base_env = os.environ.get(env_var)
    if base_env:
        base = Path(base_env).expanduser()
    elif default_base is not None:
        base = default_base
    else:
        # Fallback: current working directory, matching historical behavior that
        # typically used paths relative to the input directory.
        base = Path.cwd()

    subdir = _normalize_subdir(md_subdir)
    return base / subdir


def ensure_output_dir(path: Path) -> Path:
    """
    Ensure the given directory exists and return it.

    Idempotent and safe to call multiple times.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path

