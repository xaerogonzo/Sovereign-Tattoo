"""
sv_api.py — JS-facing API for the PyWebView GUI.

This module is a thin composer. The real implementation lives in domain
mixins under api/:

    api/alphabet_api.py      AlphabetApiMixin
    api/encode_api.py        EncodeApiMixin
    api/decode_api.py        DecodeApiMixin
    api/keyrecord_api.py     KeyRecordApiMixin
    api/vault_api.py         VaultApiMixin
    api/engine_api.py        EngineApiMixin
    api/tattoo_api.py        TattooApiMixin        (layout studio + OCR)
    api/tattoo_log_api.py    TattooLogApiMixin     (personal tattoo dossier)
    api/settings_api.py      SettingsApiMixin      (get/save settings, ping, project_root)
    api/shell_api.py         ShellApiMixin         (file dialogs, clipboard, Explorer, file I/O)

Shared infrastructure (settings, KV pipeline helpers, key-card parsing) is in
api/_helpers.py. Every method returns {'ok': bool, ...} and never raises.
"""

from __future__ import annotations

from typing import Any

from api.alphabet_api import AlphabetApiMixin
from api.decode_api import DecodeApiMixin
from api.encode_api import EncodeApiMixin
from api.engine_api import EngineApiMixin
from api.keyrecord_api import KeyRecordApiMixin
from api.settings_api import SettingsApiMixin
from api.shell_api import ShellApiMixin
from api.tattoo_api import TattooApiMixin
from api.tattoo_log_api import TattooLogApiMixin
from api.vault_api import VaultApiMixin


class SovereignApi(
    AlphabetApiMixin,
    EncodeApiMixin,
    DecodeApiMixin,
    KeyRecordApiMixin,
    VaultApiMixin,
    EngineApiMixin,
    TattooApiMixin,
    TattooLogApiMixin,
    SettingsApiMixin,
    ShellApiMixin,
):
    """
    All public methods are callable from JS as `pywebview.api.<method>(...)`.
    Returns are auto-converted to JS objects. Don't return non-JSON types.

    Method surface is inherited from the seven domain mixins above. This class
    only owns the window reference used by file dialogs.
    """

    # ----- Window reference (set after window creation) -----
    _window: Any = None

    def attach_window(self, window: Any) -> None:
        self._window = window
