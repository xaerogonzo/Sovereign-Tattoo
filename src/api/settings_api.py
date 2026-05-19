"""SettingsApiMixin — settings persistence, project root, and API ping.

OS-shell utilities (file dialogs, clipboard, Explorer, file helpers) live in
ShellApiMixin (shell_api.py). Add new setting keys in ``_read_settings`` /
``_write_settings`` inside _helpers.py; no changes needed here.
"""

from __future__ import annotations

from typing import Any

from ._helpers import _project_root, _read_settings, _write_settings


class SettingsApiMixin:
    """Settings persistence + project introspection."""

    def get_settings(self) -> dict[str, Any]:
        return {'ok': True, 'settings': _read_settings()}

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        try:
            current = _read_settings()
            current.update(settings)
            _write_settings(current)
            return {'ok': True, 'settings': current}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def project_root(self) -> dict[str, Any]:
        return {'ok': True, 'path': str(_project_root())}

    def ping(self) -> dict[str, Any]:
        """Sanity check from JS console."""
        return {'ok': True, 'message': 'Sovereign API is alive', 'version': '1.0'}
