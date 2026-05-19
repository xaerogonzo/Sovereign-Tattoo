"""VaultApiMixin — Windows Credential Manager (keyring) + key card listing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sv_keyring

from ._helpers import _parse_keycard, _project_root, _read_settings


class VaultApiMixin:
    """Keyring entries + on-disk key card discovery."""

    def vault_list(self) -> dict[str, Any]:
        return {'ok': True, 'entries': sv_keyring.list_entries()}

    def vault_delete(self, label: str) -> dict[str, Any]:
        return sv_keyring.delete_password(label)

    def vault_label_for_file(self, in_path: str) -> dict[str, Any]:
        try:
            label = sv_keyring.file_label(in_path)
            has = sv_keyring.get_password(label) is not None
            return {'ok': True, 'label': label, 'stored': has}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def list_keycards(self, folder: str | None = None) -> dict[str, Any]:
        if folder is None:
            folder = _read_settings()['vault_folder']
        p = Path(folder)
        if not p.exists():
            return {'ok': True, 'folder': str(p), 'cards': []}
        cards = []
        for f in sorted(p.glob('*.keycard.txt')) + sorted(p.glob('*.keycard')):
            cards.append(_parse_keycard(f))
        # Also include any .keycard.txt files in the project root
        root = _project_root()
        for f in sorted(root.glob('*.keycard.txt')):
            cards.append(_parse_keycard(f))
        return {'ok': True, 'folder': str(p), 'cards': cards}

    def read_keycard(self, path: str) -> dict[str, Any]:
        try:
            text = Path(path).read_text(encoding='utf-8', errors='replace')
            return {'ok': True, 'content': text}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
