@D:\Claude Co worker\Token Save\templates\project-baseline.md

# CLAUDE.md — Sovereign Tattoo Developer Guide

This file is read by Claude at the start of every session. Keep it current after major changes.

---

## What This Project Is

**Sovereign Tattoo** is a Windows toolkit for encoding binary files into plain-text strings using custom character alphabets, with optional AES-256 encryption. Primary use case: permanently storing encoded data as a tattoo. Secondary use: general cryptographic archival.

**Core constraint:** encoded text must be legible on aged skin — Base 32 (all-caps + digits, no ambiguous characters) is the default tattoo alphabet.

---

## Current Project State

### Architecture in One Line
> JS/HTML GUI (PyWebView) → Python API (src/) → PowerShell engine (sv_core.ps1) → encoded output

### File Index

```
Root/
├── sovereign_gui.py            Entry point — PyWebView window, loads gui/index.html
├── Sovereign_GUI.bat           Convenience launcher (drag-drop compatible)
├── CLAUDE.md                   This file
├── requirements.txt            Python deps: pywebview, keyring, Pillow, optional pytesseract
│
├── scripts/                    Project tooling — keep root uncluttered
│   ├── build.bat               Double-click to compile Sovereign Tattoo (calls build.py)
│   ├── build.py                Nuitka compile pipeline (standalone + onefile)
│   ├── install_tesseract.py    Portable Tesseract installer (bin/tesseract/ + tessdata_best)
│   ├── install_tesseract.bat   Double-click wrapper for install_tesseract.py
│   └── templates/              Unconfigured PS build template stubs (not for direct use)
│
├── sv_core.ps1                 PowerShell engine — ALL encoding/decoding/crypto logic
├── sovereign.cfg               Legacy config (OpenSSL path for legacy .bat workflow)
│
├── data/                       Runtime data store — JSON records + GUI config (auto-created on first write)
│   ├── sv_lib.json             Alphabet library (builtins + custom alphabets)
│   ├── sv_keyring_index.json   Vault metadata index (no passwords stored here)
│   ├── sv_key_records.json     Key Vault records — portable JSON, no passwords, travels with app folder
│   ├── sv_tattoo_log.json      Personal tattoo dossier — aesthetic/layout layer (auto-created)
│   └── sovereign_gui.cfg       GUI settings — auto-created on first Settings save
│
├── legacy/                     Pre-GUI workflow — retained for compatibility; not touched by the GUI
│   ├── sovereign_alphabet_editor_v2.html   Standalone HTML alphabet builder
│   └── scripts/
│       ├── Sovereign_Encode.bat   Drag-drop encoder
│       ├── Sovereign_Decode.bat   Drag-drop decoder
│       ├── Sovereign_Config.bat   Config + library manager
│       └── sv_import.bat          .svlib importer
│
├── src/                        Python source modules
│   ├── __init__.py
│   ├── sv_api.py               Thin composer — SovereignApi inherits from api/*Mixin classes
│   ├── sv_bridge.py            Subprocess wrapper around sv_core.ps1
│   ├── sv_keyring.py           Windows Credential Manager wrapper (keyring lib)
│   ├── sv_kvcrypto.py          Key Vault crypto: kv_encrypt/kv_decrypt (PBKDF2+OpenSSL), recovery HTML builder
│   ├── sv_keyrecord.py         Key record CRUD, integrity check, export (card + recovery.html)
│   ├── sv_compress.py          Compression layer: zlib-raw, lzma-raw; CV1 header helpers; dispatches external algos to sv_engines
│   ├── sv_engines.py           Registry & management for external engines (LPAQ8, PAQ8O, ZPAQ); install/remove/discover in bin/
│   ├── sv_tattoo.py            Tattoo Studio layout engine: 40 layouts, arc-length-correct glyph placement, _walk_polygon_path helper
│   ├── sv_tattoo_log.py        Personal tattoo dossier CRUD (My Tattoos); stores sv_tattoo_log.json
│   └── api/                    Domain-specific mixins composed into SovereignApi
│       ├── __init__.py
│       ├── _helpers.py         Shared infrastructure: settings, KV pipeline helpers (_KvError + _kv_*), key-card parsing
│       ├── alphabet_api.py     list/save/delete alphabets, import .svlib, key cards
│       ├── encode_api.py       encode, encode_text, encode_keyvault
│       ├── decode_api.py       decode, tryall, peek_header, decode_keyvault
│       ├── keyrecord_api.py    keyrecord_list/get/delete/export/find_by_string
│       ├── vault_api.py        keyring entries + key card discovery
│       ├── engine_api.py       engines_list/install/remove/test, test_compress
│       ├── tattoo_api.py       tattoo_list_layouts/render_preview/export/save_layout_to_record/image_import/ocr
│       ├── tattoo_log_api.py   TattooLogApiMixin — My Tattoos CRUD, photo management, key record linking
│       ├── settings_api.py     get_settings, save_settings, project_root, ping
│       └── shell_api.py        ShellApiMixin — file dialogs, clipboard, Explorer, file read/write helpers
│
├── bin/                        External compression engines (user-installed binaries)
│   └── README.md               Engine install instructions
│
├── gui/                        Web frontend (PyWebView loads gui/index.html)
│   ├── index.html              SPA shell — 7 tabs: Encode Decode Library Editor Vault Tattoo Settings
│   ├── alphabet_editor.html    Embedded alphabet editor (pywebview.api.save_alphabet)
│   ├── css/sovereign.css       Dark theme stylesheet (loads bundled monospace via @font-face)
│   ├── fonts/                  Bundled fonts for cross-machine glyph parity
│   │   ├── DejaVuSansMono.ttf  Monospace covering ASCII + Greek + card suits + zodiac + math
│   │   └── LICENSE.txt         Bitstream Vera / DejaVu license
│   └── js/
│       ├── app.js              Shared helpers, tab routing, API wrapper, toasts
│       ├── encode.js           Encode tab — File/Text modes, encryption, FpSize
│       ├── decode.js           Decode tab — SV1 auto-detect, keyring auto-fill, TryAll
│       ├── library.js          Library tab — alphabet table, import/delete/keycard export
│       ├── vault.js            Vault tab — stored passwords, key cards, key vault records
│       ├── tattoo.js           Tattoo Studio tab — sub-nav (My Tattoos/Layout Studio/Body Map), card grid, entry editor, body map
│       └── settings.js         Settings tab
│
└── docs/
    ├── README.md               Full user-facing documentation
    ├── ARCHITECTURE.md         Technical design reference
    ├── ROADMAP.md              Feature status and future plans
    └── CHANGELOG.md            Change history
```

### Invariants — Never Break These

1. **`sv_core.ps1` is the single source of truth** for all encoding, decoding, and standard crypto. Python never reimplements any of it.
2. **All Python API methods return `{'ok': bool, ...}`** and never raise exceptions to the JS layer.
3. **Legacy `.bat` files are untouched** — the GUI is strictly additive.
4. **`sv_keyring_index.json` never contains passwords** — metadata (hint, created timestamp) only.
5. **`sv_key_records.json` never contains passwords** — it stores salt/IV (not passwords). Passwords are entered by the user or optionally cached in Windows Credential Manager.
6. **`src/` modules use `__file__` → parent search** to find `sv_core.ps1`, so they work whether run from `src/` directly or imported from the project root.
7. **KV encryption layers on top of, not inside, sv_core.ps1** — Python encrypts first, then calls PowerShell to base-encode (without `-Password`). Decoding reverses: PowerShell base-decodes, Python decrypts.

---

## Key Commands

```powershell
# Launch the GUI
python sovereign_gui.py

# Quick bridge self-test — lists all alphabets via sv_core.ps1
python src/sv_bridge.py

# API smoke test from any shell (project root)
python -c "import sys; sys.path.insert(0,'src'); from sv_api import SovereignApi; print(SovereignApi().ping())"

# Encode a text string via CLI (quick sanity check)
python -c "
import sys; sys.path.insert(0,'src')
from sv_api import SovereignApi
r = SovereignApi().encode_text({'text':'hello','alph_id':'b32','selfdesc':True,'fpsize':'2'})
print(r)
"
```

---

## Documentation Maintenance Rules

After any session that ships changes, update docs as appropriate before finishing:

| What changed | Update |
|---|---|
| New feature or user-visible behavior | `docs/CHANGELOG.md` entry + `docs/README.md` if workflow changes |
| Module added/moved, data flow changed | `docs/ARCHITECTURE.md` |
| Phase completed or new feature planned | `docs/ROADMAP.md` |
| File index above is stale | Update **File Index** section in this file |

**Minimum rule:** every session that ships a feature adds a `docs/CHANGELOG.md` entry.

---

## Token Efficiency Guidelines

- **Read `docs/ARCHITECTURE.md` first** when orientation is needed — don't re-scan source files for context you can get from docs.
- **Use `TodoWrite`** for any task with 3+ discrete steps so progress survives context compaction.
- **Use `/compact`** when the conversation is long and the current sub-task is complete.
- **Read files with `offset`/`limit`** when a Grep shows the relevant line range — don't read whole files for a small fix.
- **Reference this file** for project state rather than re-scanning the directory each session.
- After a substantial implementation session, **update the File Index above** so the next session starts oriented.
- When reading large JS or Python files, **Grep for the function name first** to find the exact line, then Read with a small window.
