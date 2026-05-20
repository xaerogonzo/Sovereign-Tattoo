"""SettingsApiMixin — settings persistence, project root, and API ping.

OS-shell utilities (file dialogs, clipboard, Explorer, file helpers) live in
ShellApiMixin (shell_api.py). Add new setting keys in ``_read_settings`` /
``_write_settings`` inside _helpers.py; no changes needed here.

Anthropic API key is stored in Windows Credential Manager (not in the settings
JSON) using a dedicated service name so it never appears in the Vault tab list.
"""

from __future__ import annotations

from typing import Any

import keyring

from ._helpers import _project_root, _read_settings, _write_settings

# Separate service name keeps the Claude API key out of the vault entry list.
_ANTHROPIC_SERVICE = 'sovereign-tattoo-config'
_ANTHROPIC_USER    = 'anthropic_api_key'


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

    # ------------------------------------------------------------------
    # Anthropic API key — stored in Windows Credential Manager
    # ------------------------------------------------------------------

    def get_anthropic_key_status(self) -> dict[str, Any]:
        """Return whether an Anthropic API key is configured (never the key itself)."""
        try:
            val = keyring.get_password(_ANTHROPIC_SERVICE, _ANTHROPIC_USER)
            return {'ok': True, 'configured': bool(val)}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'configured': False}

    def save_anthropic_key(self, key: str) -> dict[str, Any]:
        """Save an Anthropic API key to Windows Credential Manager."""
        key = (key or '').strip()
        if not key:
            return {'ok': False, 'error': 'API key cannot be empty'}
        if not key.startswith('sk-ant-'):
            return {'ok': False, 'error': 'Key does not look like an Anthropic API key (should start with sk-ant-)'}
        try:
            keyring.set_password(_ANTHROPIC_SERVICE, _ANTHROPIC_USER, key)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': f'Credential Manager write failed: {e}'}

    def delete_anthropic_key(self) -> dict[str, Any]:
        """Remove the Anthropic API key from Windows Credential Manager."""
        try:
            keyring.delete_password(_ANTHROPIC_SERVICE, _ANTHROPIC_USER)
        except Exception:
            pass  # already gone
        return {'ok': True}
