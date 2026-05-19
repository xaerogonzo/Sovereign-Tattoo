"""
sovereign_gui.py - Entry point for the Sovereign Tattoo unified GUI.

Launches a PyWebView window that loads gui/index.html. All Python operations
are exposed to JS via the SovereignApi class (see src/sv_api.py).

Usage:
    python sovereign_gui.py
    python sovereign_gui.py <path>     # drag-drop entry: pre-populate Decode tab
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to the module search path so sv_api, sv_bridge, sv_keyring are importable.
_here = Path(__file__).resolve().parent
_src = _here / 'src'
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import webview

from sv_api import SovereignApi


def main() -> int:
    here = Path(__file__).resolve().parent
    index = here / 'gui' / 'index.html'
    if not index.exists():
        print(f'ERROR: GUI files missing at {index}')
        return 1

    api = SovereignApi()

    # Optional initial file argument (drag-drop onto the .py or the future .exe)
    initial_file = ''
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.exists():
            initial_file = str(candidate.resolve())

    # Pass the initial file via a query parameter so JS can pick it up on load.
    url = index.as_uri()
    if initial_file:
        url += '?initial=' + initial_file.replace('\\', '/').replace(' ', '%20')

    window = webview.create_window(
        title='Sovereign Tattoo',
        url=url,
        js_api=api,
        width=1100,
        height=780,
        min_size=(900, 600),
        background_color='#0f172a',
    )
    api.attach_window(window)

    webview.start(debug=True)  # debug=True enables the dev-tools right-click menu
    return 0


if __name__ == '__main__':
    sys.exit(main())
