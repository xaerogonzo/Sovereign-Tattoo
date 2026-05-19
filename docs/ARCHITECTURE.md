# Architecture — Sovereign Tattoo

## Overview

Sovereign Tattoo has two independent but complementary interfaces:

1. **Legacy CLI** — four `.bat` files that shell out directly to `sv_core.ps1`. Menu-driven, drag-drop compatible. Fully functional standalone.
2. **Unified GUI** — a PyWebView single-page application exposing the same PowerShell engine through a Python API bridge and an HTML/JS frontend.

Both interfaces share the same `sv_core.ps1` engine and `sv_lib.json` library. Adding or removing alphabets in one is immediately reflected in the other.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  PyWebView window  (Edge WebView2 / Chromium)               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  gui/index.html  —  6-tab SPA                         │  │
│  │                                                       │  │
│  │  Encode │ Decode │ Library │ Editor │ Vault │ Settings │  │
│  └──────────────────────┬────────────────────────────────┘  │
└─────────────────────────│───────────────────────────────────┘
                          │  pywebview.api.*  (JS ↔ Python)
                          ▼
              ┌───────────────────────┐
              │  src/sv_api.py        │  SovereignApi class
              │  (thin orchestration) │
              └────────┬──────────────┘
                       │
          ┌────────────┴──────────────┐
          ▼                           ▼
 src/sv_bridge.py           src/sv_keyring.py
 Subprocess wrapper          Windows Credential
 around sv_core.ps1          Manager (via keyring)
          │
          ▼
 sv_core.ps1  ◄──────── sv_lib.json
 PowerShell engine       Alphabet library
 (ALL crypto/encoding)
          │
          ▼
 Output files  (.b32, .svb32, .keycard.txt, etc.)
```

**Principle:** Python is a thin orchestration layer only. Every encode, decode, and crypto operation lives in `sv_core.ps1` and is never reimplemented in Python.

---

## Module Reference

### `sv_core.ps1` — PowerShell Engine
The single source of truth for all data transformation. Called by both the `.bat` files directly and by `sv_bridge.py` via subprocess.

**Modes** (invoked via `-Mode`):

| Mode | Description |
|------|-------------|
| `Encode` | Encode a file to base-N text, optional AES-256 |
| `Decode` | Decode base-N text back to binary |
| `TryAll` | Brute-force all alphabets on an encoded file |
| `ListLib` | Emit tab-separated alphabet table |
| `KeyCard` | Generate a `.keycard.txt` recovery card |

**Output format:** `key:value` lines on stdout. `sv_bridge._parse_kv()` converts these to Python dicts.

**Key parameters:**

| Parameter | Values | Notes |
|-----------|--------|-------|
| `-AlphId` | `hex`, `b32`, `b37`, ... | Alphabet to use |
| `-InFile` / `-OutFile` | file paths | Input and output |
| `-Password` | string | Activates AES-256 |
| `-Salt` | `salt` / `nosalt` | OpenSSL salt header mode |
| `-SelfDesc` | switch | Prepend `SV1|fp:...|b:...|` header |
| `-FpSize` | `0` / `2` / `8` | Fingerprint length in SV1 header |
| `-DualVerify` | switch | Cross-check encode against hex independently |

---

### `src/sv_bridge.py` — Python↔PowerShell Bridge

Wraps `sv_core.ps1` calls. Never exposed to JS directly — `sv_api.py` calls it.

**Key internals:**
- `project_root()` — walks `__file__` → parent until `sv_core.ps1` is found (supports `src/` nesting)
- `_run_powershell(args)` — runs with `CREATE_NO_WINDOW` flag, captures stdout+stderr
- `_parse_kv(output)` — converts `KEY:value\nHIT:...\n` lines into a dict with `hits` list
- `SovereignError` — internal exception, caught at API boundary and returned as `{ok: false, error: ...}`

**Library operations** (pure Python, no PowerShell):
- `read_library()` / `write_library()` — read/write `sv_lib.json`
- `import_svlib()`, `save_alphabet()`, `delete_alphabet()` — library CRUD

---

### `src/sv_api.py` — JS-Facing API

`class SovereignApi` — every public method is callable from JS as `pywebview.api.method(...)`.

**Method groups:**

| Group | Methods |
|-------|---------|
| Alphabets | `list_alphabets`, `save_alphabet`, `delete_alphabet`, `import_svlib` |
| Encode | `encode`, `encode_text`, `key_card` |
| Decode | `decode`, `tryall`, `peek_header` |
| Vault | `vault_list`, `vault_delete`, `vault_label_for_file`, `list_keycards`, `read_keycard` |
| File I/O | `open_file_dialog`, `file_info`, `read_text_preview`, `read_encoded_text`, `write_text_file` |
| Settings | `get_settings`, `save_settings` |
| Utilities | `copy_to_clipboard`, `open_folder`, `project_root`, `ping` |

**Contract:** every method returns a JSON-serializable dict. On failure: `{'ok': False, 'error': '...'}`. On success: `{'ok': True, ...}`.

**`encode_text(params)`** — special case: accepts `text` string instead of `in_path`. Writes UTF-8 temp file → encodes → reads back encoded string → deletes temp input → returns `encoded_text` inline.

**Settings** are persisted in `sovereign_gui.cfg` (JSON). Defaults:

| Key | Default |
|-----|---------|
| `default_alphabet` | `b32` |
| `default_fpsize` | `8` |
| `default_salt_mode` | `salt` |
| `default_selfdesc` | `false` |
| `vault_folder` | `%USERPROFILE%\Documents\Sovereign\KeyCards` |
| `openssl_path` | `''` (assumes on PATH) |

---

### `src/sv_keyring.py` — Password Vault

Wraps the `keyring` Python library (Windows Credential Manager backend).

- **Service name:** `'sovereign-tattoo'`
- **Label:** `sha256(first 4KB of file + filesize)[:16]` — stable across moves if content unchanged
- **Index:** `sv_keyring_index.json` at project root — stores `{label: {hint, created}}` only, never passwords
- **Why an index?** The OS keyring API doesn't enumerate entries portably across backends

---

### `sovereign_gui.py` — Entry Point

- Adds `src/` to `sys.path`
- Creates the PyWebView window pointed at `gui/index.html`
- Accepts an optional file path argument (drag-drop onto the `.py` or `.bat`); routes to Decode tab via `?initial=` URL query parameter
- `debug=True` enables right-click DevTools (Edge DevTools panel opens alongside the window — this is expected)

---

## Frontend (gui/)

### Tab Architecture

Each tab is a `<section data-panel="tabname">` in `index.html`. Tab modules in `js/` register themselves on `window.Tabs`:

```js
Tabs.encode = (() => {
  function init() { ... }
  function onShow() { ... }  // called on tab switch
  return { init, onShow };
})();
```

`app.js` calls `Tabs.*.init()` on `pywebviewready` and `Tabs.*.onShow()` on tab switch.

### API Call Pattern

```js
const r = await App.api('method_name', arg1, arg2);
if (!r.ok) { App.toast(r.error, 'error'); return; }
// use r.field
```

### Shared Helpers (`app.js`)

| Helper | Purpose |
|--------|---------|
| `App.api(method, ...args)` | Awaits `pywebview.api[method](...)` |
| `App.toast(msg, type)` | Floating notification (info/success/error/warning) |
| `App.confirm(title, body)` | Promise-based modal — resolves true/false |
| `App.switchTab(name)` | Tab routing + calls `onShow` |
| `App.setupDropZone(id, cb)` | HTML5 drag-drop wiring |
| `App.estimateChars(size, base, enc, overhead)` | Live output length estimate |
| `App.getAlphabets(force)` | Cached alphabet list |
| `App.getSettings(force)` | Cached settings |
| `App.bindSegmented(id, cb)` | Segmented control event binding |

### Encode Tab Source Modes

The Encode tab has two input modes selected by a `File | Text` segmented toggle:
- **File mode:** HTML5 drag-drop zone + browse dialog → `encode(params)` API
- **Text mode:** textarea with live UTF-8 byte counter → `encode_text(params)` API (writes temp file internally, returns encoded string inline)

---

## Data Files

All runtime JSON stores live under `data/` at the project root. The directory is auto-created on
first write (each module's `_write_*` function calls `parent.mkdir(parents=True, exist_ok=True)`).

| File | Format | Notes |
|------|--------|-------|
| `data/sv_lib.json` | JSON `{alphabets: [...]}` | Each entry: `{id, name, chars, base, engine, fingerprint, builtin, notes}` |
| `data/sv_keyring_index.json` | JSON `{label: {hint, created}}` | No passwords. Auto-created by sv_keyring.py |
| `data/sv_key_records.json` | JSON `{version, entries: {id: {...}}}` | Key vault records. No passwords. Portable with the app folder. |
| `data/sv_tattoo_log.json` | JSON `{version, entries: {id: {...}}}` | Personal tattoo dossier. Aesthetic/layout layer only. Sibling to sv_key_records.json — never writes to it. |
| `data/sovereign_gui.cfg` | JSON flat dict | GUI settings. Auto-created on first save |
| `sovereign.cfg` | Plain text `KEY=value` | Legacy config read by .bat files — stays in root |
| `*.keycard.txt` | Human-readable | Recovery cards — alphabet chars + test vector |
| `*.svlib` | JSON `{entry: {...}}` | Portable alphabet export |

### Data Boundary Invariant

`sv_tattoo_log.json` and `sv_key_records.json` are **strict siblings, never parent-child**. No code in
`sv_tattoo_log.py` or `api/tattoo_log_api.py` ever opens or writes `sv_key_records.json`. The two stores
may be cross-linked by ID (`entry.key_record_id → record.id`) but the link is a foreign key pointer only.
Deleting a tattoo log entry never deletes the linked key record.

---

## Tattoo Studio Architecture

### Layout Engine (`src/sv_tattoo.py`)

All 40 layouts share two core primitives:

- **`_advance_along_path(path_fn, t0, ds)`** — given a parametric path function and a starting parameter
  value, returns the next `t` such that arc length from `t0` to `t` equals `ds`. Uses binary search with
  adaptive bisection. Guarantees character spacing is measured in true arc length, not parametric step.
- **`_tangent_angle_deg(path_fn, t, eps=1e-4)`** — returns tangent direction in degrees at parameter `t`
  via symmetric finite difference.

Polygon outlines use the additional `_walk_polygon_path` helper which:
1. Precomputes cumulative arc lengths at each vertex.
2. Binary-searches to find the enclosing edge for each character.
3. Blends tangent angles within `smooth_em` of a vertex using `_circular_lerp_angle` (unit-vector lerp
   + atan2) to prevent the rotation-snap glitch at corners.

Layouts are registered in `LAYOUT_CATALOG` as `{key, label, group, param_schema, defaults, text_exportable}`.
The API (`tattoo_api.py`) returns the catalog to the JS chip-row renderer dynamically — no hard-coded layout
names anywhere in the frontend.

### Tattoo Manager (`src/sv_tattoo_log.py`)

Tattoo entries represent real tattoos with aesthetic metadata:
- `type: "encoded" | "art"` — encoded entries link to a key record via `key_record_id`.
- `placement` — one of 51 body zone keys (matches the SVG body-map element IDs in `gui/index.html`).
- `photos` — list of relative paths under `<vault>/tattoo_images/`.
- `status` — lifecycle stage: planned → design → scheduled → fresh → healing → healed → touchup_needed → retired.

### Body Map

The `gui/index.html` Body Map sub-panel embeds two inline SVG silhouettes (front + back view). Each body zone
is an SVG shape (`<ellipse>` or `<rect>`) with `class="bz"` and `id` matching the placement enum key
(e.g. `id="forearm_l"`). The JS `refreshBodyMap()` adds `has-tattoo` / `multi-tattoo` CSS classes to zones
that contain entries. Zone hover is cross-linked between the SVG and the zone-list sidebar via
`querySelectorAll('.bz[id="..."]')` (covers both front and back SVGs). Zone click filters the My Tattoos
card grid and switches to that sub-panel.

---

## SV1 Header Format

Self-describing header prepended to encoded output when `-SelfDesc` is set:

```
SV1|fp:XXXXXXXX|b:NN|<encoded data>
SV1|fp:XX|b:NN|<encoded data>      ← FpSize=2
SV1|b:NN|<encoded data>            ← FpSize=0
```

- `fp` — first N hex chars of SHA-256 of the alphabet character string
- `b` — numeric base of the alphabet
- Decoder regex: `^SV1\|(?:fp:([0-9a-f]{2,8})\|)?b:(\d+)\|`

---

## Output Filename Convention

| Mode | Extension |
|------|-----------|
| Unencrypted | `<original>.<alphid>` e.g. `photo.jpg.b32` |
| Encrypted | `<original>.sv<alphid>` e.g. `photo.jpg.svb32` |
| Key card | `<original>.<alphid>.keycard.txt` |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| PyWebView for whole UI | Reuses the existing HTML alphabet editor seamlessly; consistent web tech |
| `keyring` / Windows Credential Manager | OS-native password storage; no master password needed |
| Embedded alphabet editor | `save_alphabet` API call replaces the .svlib download dance |
| `sv_core.ps1` unchanged | Tested crypto path is never touched by GUI changes |
| Legacy .bats untouched | GUI is additive; existing workflows keep working |
| `src/` subfolder for Python modules | Separates source from data files and launchers at project root |
| `encode_text` temp-file approach | Keeps all encoding in PowerShell; Python just writes UTF-8 bytes |
