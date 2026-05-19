"""ShellApiMixin — OS-shell utilities: file dialogs, clipboard, file I/O helpers."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

# pywebview is imported lazily for file dialogs (avoids hard dep at import time)
try:
    import webview  # type: ignore
except ImportError:
    webview = None  # type: ignore


class ShellApiMixin:
    """OS-shell utilities: file dialogs, clipboard, Explorer, and small file helpers.

    To add a new file-dialog mode: extend ``open_file_dialog``.
    To add a new shell action:     add a method here; do NOT put it in SettingsApiMixin.
    """

    # Required attribute (set by SovereignApi composer / attach_window):
    _window: Any  # type: ignore[assignment]

    # ===== File dialogs ===================================================

    def open_file_dialog(self, mode: str = 'open', default_name: str = '') -> dict[str, Any]:
        """mode: 'open' | 'save' | 'folder'"""
        if not webview or not self._window:
            return {'ok': False, 'error': 'No window context'}
        try:
            if mode == 'save':
                result = self._window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename=default_name,
                )
            elif mode == 'folder':
                result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
            else:
                result = self._window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_multiple=False,
                )
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        if not result:
            return {'ok': True, 'path': None}
        path = result[0] if isinstance(result, (list, tuple)) else result
        return {'ok': True, 'path': path}

    # ===== File info / read / write =======================================

    def file_info(self, path: str) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            return {'ok': False, 'error': 'File does not exist'}
        st = p.stat()
        return {
            'ok': True,
            'path': str(p),
            'name': p.name,
            'size': st.st_size,
            'modified': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime)),
        }

    def read_text_preview(self, path: str, max_bytes: int = 512) -> dict[str, Any]:
        """Used by Decode tab to preview small text outputs."""
        try:
            with Path(path).open('rb') as f:
                raw = f.read(max_bytes)
            try:
                text = raw.decode('utf-8')
                is_text = True
            except UnicodeDecodeError:
                text = raw.decode('latin-1', errors='replace')
                is_text = all(c.isprintable() or c in '\r\n\t' for c in text[:100])
            return {'ok': True, 'preview': text, 'is_text': is_text,
                    'truncated': Path(path).stat().st_size > max_bytes}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def read_encoded_text(self, in_path: str) -> dict[str, Any]:
        """Return the encoded text content (for copy-from-disk in Decode tab)."""
        try:
            text = Path(in_path).read_text(encoding='utf-8', errors='replace').strip()
            return {'ok': True, 'text': text, 'length': len(text)}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def write_text_file(self, out_path: str, text: str) -> dict[str, Any]:
        """Used when user pastes encoded text rather than dropping a file."""
        try:
            Path(out_path).write_text(text, encoding='utf-8')
            return {'ok': True, 'path': out_path}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ===== Clipboard / OS open ============================================

    def copy_to_clipboard(self, text: str) -> dict[str, Any]:
        """Copy text via PowerShell (avoids extra deps)."""
        try:
            subprocess.run(
                ['powershell', '-NoProfile', '-Command', 'Set-Clipboard -Value $input'],
                input=text,
                text=True,
                check=True,
                creationflags=0x08000000 if os.name == 'nt' else 0,
            )
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def open_folder(self, path: str) -> dict[str, Any]:
        """Open a folder (or the parent of a file) in Explorer."""
        p = Path(path)
        target = p if p.is_dir() else p.parent
        try:
            subprocess.Popen(['explorer', str(target)])
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def open_path(self, path: str) -> dict[str, Any]:
        """Open a file with the OS default application (Windows: os.startfile)."""
        p = Path(path)
        if not p.exists():
            return {'ok': False, 'error': f'Path does not exist: {p}'}
        try:
            if os.name == 'nt':
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(['xdg-open', str(p)])
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
