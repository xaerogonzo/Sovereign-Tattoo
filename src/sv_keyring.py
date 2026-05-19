"""
sv_keyring.py - Thin wrapper around the OS keyring (Windows Credential Manager).

Passwords are stored under service name 'sovereign-tattoo', keyed by a label.
The label is typically a SHA-256 of the encoded file's path or content prefix,
plus an optional human-readable hint.

We also keep a small JSON index of label -> {hint, created} so the Vault tab
can list entries (the OS keyring API doesn't enumerate entries portably).
The index never contains the password itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import keyring

SERVICE_NAME = 'sovereign-tattoo'


# Single authoritative root resolver lives in sv_bridge — import it here so
# every storage module agrees on what "project root" means.
from sv_bridge import project_root as _project_root  # noqa: E402


def _index_path() -> Path:
    # Co-locate the index under data/ so it travels with the project.
    return _project_root() / 'data' / 'sv_keyring_index.json'


def _read_index() -> dict[str, dict[str, Any]]:
    p = _index_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _write_index(idx: dict[str, dict[str, Any]]) -> None:
    """Atomic write via .tmp + os.replace (see sv_keyrecord._write_store)."""
    p = _index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(idx, indent=2), encoding='utf-8')
    os.replace(tmp, p)


def file_label(path: str | Path, hint: str | None = None) -> str:
    """
    Derive a stable label for a file. Uses SHA-256 of the file's first 4 KB
    plus its size, so the same encoded file always yields the same label.
    """
    p = Path(path)
    h = hashlib.sha256()
    try:
        with p.open('rb') as f:
            h.update(f.read(4096))
        h.update(str(p.stat().st_size).encode())
    except Exception:
        # Fall back to absolute path hash if file unreadable
        h.update(str(p.resolve()).encode())
    digest = h.hexdigest()[:16]
    return f'{digest}'


def save_password(label: str, password: str, hint: str | None = None) -> dict[str, Any]:
    try:
        keyring.set_password(SERVICE_NAME, label, password)
    except Exception as e:
        return {'ok': False, 'error': f'Keyring write failed: {e}'}
    idx = _read_index()
    idx[label] = {
        'hint': hint or '',
        'created': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    _write_index(idx)
    return {'ok': True, 'label': label}


def get_password(label: str) -> str | None:
    try:
        return keyring.get_password(SERVICE_NAME, label)
    except Exception:
        return None


def delete_password(label: str) -> dict[str, Any]:
    try:
        keyring.delete_password(SERVICE_NAME, label)
    except keyring.errors.PasswordDeleteError:
        pass  # tolerate missing
    except Exception as e:
        return {'ok': False, 'error': f'Keyring delete failed: {e}'}
    idx = _read_index()
    idx.pop(label, None)
    _write_index(idx)
    return {'ok': True}


def list_entries() -> list[dict[str, Any]]:
    """Return metadata only (never passwords)."""
    idx = _read_index()
    return [
        {'label': label, 'hint': meta.get('hint', ''), 'created': meta.get('created', '')}
        for label, meta in sorted(idx.items(), key=lambda kv: kv[1].get('created', ''), reverse=True)
    ]
