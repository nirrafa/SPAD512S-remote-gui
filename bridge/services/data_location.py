"""Save-path management and host path resolution.

The vendor save path may be a Windows path (``D:\\lab_data\\...``) while the
bridge in dev/tests runs on POSIX. A path that cannot be written locally
becomes a *virtual prefix*: files are stored under ``data_root`` but reported
to (and resolved from) clients with the prefix applied, mirroring where the
vendor writes on the camera host. On the production Windows host the save
path is locally absolute and is used directly.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_SEP_RE = re.compile(r"[\\/]+")


class DataLocation:
    def __init__(self, data_root: str) -> None:
        self._data_root = Path(data_root)
        self._save_path: str | None = None

    @property
    def save_path(self) -> str | None:
        return self._save_path

    def set_save_path(self, path: str) -> None:
        self._save_path = path.rstrip("\\/") or None

    def _local_save_root(self) -> Path | None:
        if self._save_path is None:
            return None
        if _WINDOWS_DRIVE_RE.match(self._save_path) and os.name != "nt":
            return None
        candidate = Path(self._save_path)
        return candidate if candidate.is_absolute() else None

    @property
    def _virtual_prefix(self) -> str | None:
        if self._save_path is not None and self._local_save_root() is None:
            return self._save_path
        return None

    @property
    def base_dir(self) -> Path:
        """Directory acquisition folders are actually created under."""
        return self._local_save_root() or self._data_root

    def display_path(self, actual: Path) -> str:
        """Map a local path to the path string reported to clients."""
        prefix = self._virtual_prefix
        if prefix is None:
            return str(actual)
        try:
            rel = actual.resolve().relative_to(self._data_root.resolve())
        except ValueError:
            return str(actual)
        return prefix + "".join("\\" + part for part in rel.parts)

    def resolve(self, requested: str) -> Path | None:
        """Resolve a client-supplied path, constrained to the data roots.

        These endpoints serve host files on an unauthenticated LAN, so any
        traversal (``..``) or absolute path escaping the configured roots
        resolves to ``None`` and must be rejected by the caller.
        """
        prefix = self._virtual_prefix
        if prefix is not None and requested.startswith(prefix):
            parts = [p for p in _SEP_RE.split(requested[len(prefix):]) if p and p != "."]
            if any(p == ".." for p in parts):
                return None
            candidate = self._data_root.joinpath(*parts)
        else:
            candidate = Path(requested)
        try:
            resolved = candidate.resolve()
        except OSError:
            return None
        for root in self._allowed_roots():
            try:
                root_resolved = root.resolve()
            except OSError:
                continue
            if resolved == root_resolved or resolved.is_relative_to(root_resolved):
                return resolved
        return None

    def _allowed_roots(self) -> list[Path]:
        roots = [self._data_root]
        local_save = self._local_save_root()
        if local_save is not None:
            roots.append(local_save)
        return roots
