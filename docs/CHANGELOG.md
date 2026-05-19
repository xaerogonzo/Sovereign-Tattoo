# Changelog — Sovereign Tattoo

All notable changes are documented here. Entries are newest-first.

---

## [Unreleased — Tattoo Manager + Full Layout Library] — 2026-05-17

### Added
- **Phase C1 — Full Layout Library (40 layouts total, up from 5).** `src/sv_tattoo.py` gains 35 new
  layout functions, three shared helpers (`_circular_lerp_angle`, `_regular_polygon_vertices`,
  `_star_vertices`, `_walk_polygon_path`), and a fully populated `LAYOUT_CATALOG`.

  | Group | Layouts |
  |---|---|
  | linear | column_single, boustrophedon, border_rect, stagger, grid_fill, pyramid_up, pyramid_down, hourglass, diamond_fill |
  | radial | arc, spiral_outward, concentric, double_ring, radial_spokes, sunburst |
  | path | zigzag, double_wave, figure8, s_curve, dna |
  | shape | triangle_up, triangle_down, diamond_outline, cross, star_5, star_6, hexagon, pentagon, heart, infinity, crescent |
  | body | sleeve_band, spine_col, bracelet, shoulder_arc |

  Polygon outlines (triangle, diamond, cross, star, hexagon, pentagon, crescent) use `_walk_polygon_path`
  which precomputes per-edge arc lengths and blends tangent angles within `smooth_em` of each vertex via
  `_circular_lerp_angle` (unit-vector lerp + atan2) — prevents the rotation-snap glitch where a glyph
  straddling a corner snaps 30–120°.

- **Phase C2 — General Tattoo Manager ("My Tattoos").** The Tattoo tab now has three sub-panels
  (sub-navigation pills):

  - **My Tattoos** — card grid of all tattoo entries (encoded + art). Supports filtering by status,
    placement, type, and free-text search. Slide-in entry editor for full CRUD:
    name, type (encoded/art), placement (51 zones, grouped), placement notes, artist, studio,
    style, status, date done, size, price, currency, ink colors (tag chips), notes.
    Photo management: import image files → stored as `<vault>/tattoo_images/<entry_id>_N.<ext>`,
    thumbnail strip in editor. Key record linking: link/unlink an encoded tattoo to a key record;
    safe-delete contract (deleting a log entry never touches `sv_key_records.json`; UI warns when
    a linked key record was NOT deleted). The ⚡ Studio button on encoded-type cards opens the
    entry in Layout Studio pre-loaded.

  - **Layout Studio** — existing content, unchanged. Gains a third source mode: "From My Tattoos"
    (dropdown of encoded tattoo log entries with linked key records).

  - **Body Map** — inline SVG body silhouette (front + back view toggle). All 51 body zones are
    clickable shapes (`class="bz"`) with `id` matching the placement enum key. Zone list sidebar
    shows tattoo counts per zone. SVG zones and list rows cross-highlight on hover (both surfaces
    linked). Clicking a zone filters the My Tattoos card grid and switches to that sub-panel.
    "Show all" button clears the filter.

- **`src/sv_tattoo_log.py`** — new module. Personal tattoo dossier CRUD:
  `create_entry`, `get_entry`, `list_entries`, `update_entry`, `delete_entry`,
  `add_photo`, `remove_photo`. Stores in `sv_tattoo_log.json` alongside `sv_key_records.json`.
  The two files are strict siblings — `sv_tattoo_log.py` never imports or writes `sv_key_records.json`.
  50+ placement zone constants (`PLACEMENTS`) and status enum (`STATUSES`).

- **`src/api/tattoo_log_api.py`** — new `TattooLogApiMixin` wired into `SovereignApi` MRO.
  Methods: `tattoo_log_list`, `tattoo_log_get`, `tattoo_log_create`, `tattoo_log_update`,
  `tattoo_log_delete`, `tattoo_log_add_photo`, `tattoo_log_remove_photo`,
  `tattoo_log_link_record`, `tattoo_log_unlink_record`.

### Changed
- **`gui/index.html`** — Tattoo tab restructured with sub-nav. Layout Studio content moved
  into `#tattoo-sub-studio`. `#tattoo-sub-log` and `#tattoo-sub-map` added.
  Layout Studio source options extended with "From My Tattoos" radio + `#tattoo-log-entry-picker`.
- **`gui/js/tattoo.js`** — complete rewrite to integrate sub-nav routing, My Tattoos state +
  card rendering, slide-in entry editor, photo management, key record link/unlink UI,
  Body Map zone highlighting and cross-linking, and "From My Tattoos" source mode.
- **`gui/css/sovereign.css`** — styles added for: sub-nav pills (`.sub-tab`), card grid
  (`.tlog-card`), status/type badges, slide-in editor (`.tlog-editor`), field rows,
  ink-color tag chips, photo strip (`.tlog-photo-thumb`), body map layout and SVG zone
  states (`.bz`, `.has-tattoo`, `.multi-tattoo`, `.active`, `.hovered`), zone list sidebar.

---

## [Unreleased — API refactor & Unicode alphabets] — 2026-05-17

### Changed
- **Legacy assets relocated to `legacy/`.** The four pre-GUI workflow batch files (`Sovereign_Encode.bat`, `Sovereign_Decode.bat`, `Sovereign_Config.bat`, `sv_import.bat`) moved from the project root to `legacy/scripts/`. The standalone `sovereign_alphabet_editor_v2.html` moved to `legacy/`. Each `.bat`'s internal path resolution was updated from `%~dp0sv_core.ps1` (own directory) to `%~dp0..\..\sv_core.ps1` via a normalising `for` loop (`for %%A in ("%~dp0..\..") do set "root=%%~fA\"`), so they still find `sv_core.ps1`, `sv_lib.json`, and `sovereign.cfg` at the actual project root. `sovereign.cfg` itself stays at root — it's a data file the legacy `.bat`s read/write, not a script. Net effect: root project listing now has 10 entries instead of 17 with no functional change to either modern or legacy workflows.

### Added
- **`scripts/` folder.** Project tooling moved out of root to keep things tidy: `build_nuitka.py`, `install_tesseract.py`, plus matching `.bat` wrappers for double-click invocation. Both Python scripts now use an upward-walk `_find_project_root()` that anchors on `sv_core.ps1`, so they work from any cwd (project root, scripts/, or anywhere else). The `.bat` wrappers prefer the `py` launcher and fall back to `python`, forward all args, and pause only when launched without arguments (so double-clickers see output but command-line users don't get an extra keypress).
- **Portable Tesseract install (`install_tesseract.py`).** New helper script at the project root that downloads the UB-Mannheim Tesseract installer, silent-installs it to a temp scratch directory with `/CURRENTUSER` (no UAC), copies the resulting tree to `bin/tesseract/`, then silent-uninstalls the scratch install to remove registry entries and Start Menu shortcuts. After install, it replaces the installer-shipped tessdata with the higher-accuracy `tessdata_best/eng.traineddata` + `tessdata_best/osd.traineddata` (~32 MB combined). Final on-disk footprint ~75 MB under `bin/tesseract/`; the install is unregistered with the OS so uninstalling Tesseract elsewhere can't trash it. `_TesseractAdapter._resolve_cmd()` now checks `bin/tesseract/tesseract.exe` first (ahead of Settings override / PATH / common install dirs) so the bundle is auto-detected with zero configuration. `TESSDATA_PREFIX` is set transiently when the bundled binary is in use so it finds the right language data without leaking the env var. Nuitka builds pick up the bundle automatically because `build_nuitka.py` already includes `bin/` when non-empty. Usage: `python install_tesseract.py` (or `--force` to reinstall, `--remove` to delete).
- **Tattoo Studio Phase B3 — OCR Hybrid mode.** New "OCR Review" pane on the Tattoo tab. Three pluggable recognition adapters:
  - `manual` — always available; returns an empty string so the user types from scratch with the image as reference.
  - `tesseract` — Tesseract OCR via `pytesseract`. Auto-detects the binary on PATH and common Windows install locations, falls back to a user-configurable path in Settings. ASCII-only; the alphabet's `chars` field is passed as `tessedit_char_whitelist` for ASCII-subset alphabets to dramatically improve accuracy.
  - `custom_glyph` — stub for Phase B4 (planned: per-alphabet template matching for Unicode/symbol alphabets that mainstream OCR can't handle).
  Keyboard-first review editor (per Gemini's critique that manual correction is the primary path, not a fallback): editor auto-focuses on OCR completion, **Ctrl+Enter** = "Use this text →" (routes to Decode tab pre-filled), **Esc** = discard, **Tab** cycles fields. New API methods: `tattoo_adapters_list`, `tattoo_image_recognize`. New setting: `tesseract_path` with a Settings UI field.
- **Tattoo Studio Phase B2 — PNG export + reference image manager.** PNG raster export via Pillow using the bundled DejaVu Sans Mono (pixel-perfect parity with the Canvas live preview). Rotated glyphs (circle/spiral/wave) rendered via padded transparent intermediate images + alpha-channel-tight cropping after `Image.rotate(expand=True)` to avoid edge-clipping on wide characters (per Gemini's watchpoint). New "Reference image" pane on the Tattoo tab: drop a photo, stencil mockup, or any picture of an encoded string → sidecar-stored under `<vault>/tattoo_images/<rec_id>.<ext>` with the path recorded in the key record. Auto-displays as a thumbnail when reopening the record. New API methods: `tattoo_image_import`, `tattoo_image_remove`. New `_tattoo_dirs()` helper in `api/_helpers.py` for vault subfolder discovery.
- **Nuitka build pipeline.** `build_nuitka.py` at the project root compiles the whole app into a standalone or onefile distribution. Bundles `sv_core.ps1`, `sv_lib.json`, the entire `gui/` tree (including the bundled font), and any compression engines under `bin/`. Skips Tesseract and OpenSSL on the assumption the user installs them separately. `_project_root()` and `_bundled_font_path()` use upward-walk-from-`__file__` resolution so they work identically in source and frozen mode.
- **`requirements.txt`** at the project root documenting `pywebview`, `keyring`, `Pillow`, and the optional `pytesseract` dep.
- **Tattoo Studio (Phase B1 MVP).** New "Tattoo" tab in the GUI that renders an encoded string as a tattoo-ready visual layout. Ships with five layouts: paragraph, multi-column matrix, circle, inward spiral, and wave. Live HTML Canvas preview updates in ~150 ms as you tweak parameters. Export as SVG (self-contained, scalable for tattoo stencil software) or plain text (paragraph/column only). Layout choice can be saved to the key record so reopening a record restores the chosen layout. New module `src/sv_tattoo.py` implements the layout math with an arc-length-correct path walker (`_advance_along_path`) — characters along curves are spaced by *arc length* not parametric step, preventing the classic bunching-on-inner-radii / stretching-on-outer-radii failure mode. Validated by 21 self-tests including known closed-form arc lengths (half-circumference of unit circle = π).
- **Bundled DejaVu Sans Mono** (`gui/fonts/DejaVuSansMono.ttf`, ~333 KB, Bitstream Vera license). Wired via `@font-face` as font family "Sovereign Mono". Provides cross-machine pixel-perfect glyph parity — same font on dev machine, in the GUI Canvas, and in exported SVG. Covers all alphabet ranges including card suits (♠♣♥♦), zodiac (♈–♓), Greek (α–ω), math (∞∑∫), currency, and block elements. Original plan called for JetBrains Mono Regular but coverage check rejected it (1,373 codepoints, missing all our symbol categories); DejaVu has 3,324 codepoints and covered every glyph in `UNICODE_GROUPS`.
- **`TattooApiMixin`** at `src/api/tattoo_api.py` with four methods: `tattoo_list_layouts`, `tattoo_render_preview`, `tattoo_export`, `tattoo_save_layout_to_record`. Added to `SovereignApi` MRO between `EngineApiMixin` and `SettingsApiMixin`.
- **Backward-compatible schema additions** to key records: `tattoo_layout` (string) and `tattoo_layout_params` (dict). Older records work unchanged.

### Changed
- **`sv_engines.compress` / `sv_engines.decompress` refactored** (Phase A of the Tattoo Studio plan). The two mirror-image functions (CC 13 each, 9 return paths each, ~75 lines each) were decomposed into three shared helpers: `_resolve_engine`, `_run_in_place_engine` (PAQ8O-style), and `_run_explicit_engine` (LPAQ8-style). Each public function is now a 9-line orchestrator. The in-place helper uses `tempfile.TemporaryDirectory()` for guaranteed cleanup on interrupt and process-unique paths for future thread safety. Error messages now consistently carry the `op_label` ("compress" vs "decompress") so failures from batch round-trips identify which side broke. Net effect: `compress`/`decompress` dropped out of tokensave's top-10 complexity list entirely; the heaviest new helper lands at CC 6 (down from 13). Public signatures unchanged — no callers needed updating.

- **`src/sv_api.py` split into mixins.** The 1,249-line god class was decomposed into seven domain-specific mixin files under `src/api/`:
  `alphabet_api.py`, `encode_api.py`, `decode_api.py`, `keyrecord_api.py`, `vault_api.py`, `engine_api.py`, `settings_api.py`. Shared infrastructure (settings persistence, KV pipeline helpers, key-card parsing) lives in `src/api/_helpers.py`. `sv_api.py` is now a 53-line composer. Public API surface unchanged — `from sv_api import SovereignApi` still works.
- **`encode_keyvault` cyclomatic complexity dropped from 31 → low single digits** by extracting 6 focused helpers (`_kv_resolve_input`, `_kv_hash_source`, `_kv_encrypt_to_temp`, `_kv_base_encode`, `_kv_build_tattoo_string`, `_kv_lookup_alphabet`) and introducing a `_KvError` exception caught at the boundary. Body shrank from 224 → 131 lines and reads as a numbered 9-step pipeline.
- **`decode_keyvault` cyclomatic complexity dropped from 26 → low single digits** via parallel helpers (`_kv_get_encoded_string`, `_kv_find_record`, `_kv_get_password`, `_kv_strip_headers`, `_kv_base_decode`, `_kv_decrypt`, `_kv_decompress_or_move`, `_kv_text_preview`). Body shrank from 161 → 75 lines.

### Added
- **Unicode symbol alphabets.** Extended `gui/alphabet_editor.html` with ~250 curated symbols across 20 categories (card suits, stars, geometric shapes, arrows, Greek, math, currency, musical, zodiac, planets, misc, letterlike, blocks) in a collapsible "Extended Unicode symbols" section. Plus a paste-any-character input for one-off symbols.
- **Confusable warnings** for Greek uppercase look-alikes (Α/Β/Ε/Η/Ι/Κ/Μ/Ν/Ο/Ρ/Τ/Υ/Χ) and lowercase ο/ν, with specific tooltip messages.
- **`b41` preset:** `b37` Tattoo-Safe + `♠♣♥♦` — a ready-to-use tattoo-friendly extended alphabet.
- **Duplicate-character + minimum-length validation** in `save_alphabet`. Previously a duplicate char would silently corrupt encode/decode (`.IndexOf()` returns the first match only).
- **"Save key record to vault" checkbox** on Encode tab (KV mode). Lets users encode without persisting a vault entry — useful for one-off ciphertext generation.
- **Engine subdirectory discovery** in `sv_engines.py`: `engine_path()` now does recursive `rglob()` search and picks the newest match by mtime. `list_engines()` reports `is_canonical: bool` so the Settings UI can show a "found in subfolder" hint and hide the Remove button for non-canonical installs.

### Fixed
- **`sv_core.ps1` Unicode I/O.** Encode output now writes UTF-8 (no BOM) instead of ASCII (lines 296, 322, 389). This is the single change that unblocks the entire Unicode alphabet pipeline — everything else in PowerShell was already string-level Unicode-capable.
- **`sv_bridge.save_alphabet`** sets `notes=''` and `builtin=False` defaults so `sv_core.ps1` doesn't throw `PropertyNotFoundException` on custom alphabets missing those fields.
- **PAQ8O compression** now runs with `cwd=tmpdir` and a fixed `sv_data` basename, so the archive stores a relative path (`./sv_data`) — decompressible from any fresh temp dir. Default level lowered from `-8` to `-4` (~135 MB RAM instead of 2 GB).
- **`tmp_enc` NameError** in pre-refactor `encode_keyvault` when KV crypto raised before the variable was bound.

---

## [Unreleased — Self-hosted Compression Engines] — 2026-05-16

### Added
- **`src/sv_engines.py`** — registry of external compression engines, install/remove/discovery in `bin/` folder at project root.
- **`bin/` folder** auto-created on first launch; ships with a README explaining how to install LPAQ8 / PAQ8O / ZPAQ.
- **Registry** for LPAQ8 (public domain), PAQ8O (GPL), ZPAQ (public domain, listed but not yet wired). Each entry includes expected filename, CLI signature, homepage URL, and license.
- **Settings → Compression engines** section: per-engine status card showing installed state, path, license, homepage link, with "Browse for binary…", "Test round-trip", "Remove", and "Copy URL" buttons.
- **PAQ8O support** on the Encode tab (alongside LPAQ8). Buttons auto-disable when binary not present in `bin/`.
- **`engines_list` / `engine_install` / `engine_remove` / `engine_test` API methods.**
- **Multi-char CV1 codes** — registry adds `lp` (LPAQ8), `po` (PAQ8O), `zp` (ZPAQ) on top of the existing single-char `z` (zlib) and `l` (lzma). CV1 regex updated to accept 1–2 char codes.
- **Auto compression** iterates every installed external engine alongside stdlib algos and picks the absolute winner.

### Changed
- Sovereign no longer depends on a PEAzip install. The deprecated `lpaq_path` setting is retained for compatibility but ignored — engines now resolve via `bin/<filename>` lookup.
- Removed Settings "LPAQ binary" path field and "Auto-find" button (replaced by Engines section).
- Removed `find_lpaq` API method (kept `sv_compress.find_lpaq` as a thin shim that delegates to `sv_engines`).

### Why no auto-download?
Initial design is browse-only. Antivirus tooling regularly quarantines `.exe` files fetched from untrusted hosts, Matt Mahoney's site is HTTP-only (no transport security), and shipping a verified SHA-256 per engine requires more vetting than was reasonable for this iteration. Users open the homepage link in their browser, download the official zip, extract, and either drop the `.exe` into `bin/` or use the Browse button.

---

## [Unreleased — Compression Layer] — 2026-05-16

### Added
- **Compression layer** (`src/sv_compress.py`) sitting between source data and encryption.
  Raw-mode algorithms (zero-byte stream headers): **zlib** (raw deflate, `wbits=-15`), **lzma** (`FORMAT_RAW`, LZMA2 preset 9 + EXTREME), plus optional external **LPAQ** binary.
- **Auto compression mode** — tries every available algorithm + uncompressed baseline, picks the smallest. Falls back to "none" if nothing helps.
- **`CV1|c:X|` header** — 6-char prefix outside any SV1/KV header that records which algorithm was used (`z`=zlib, `l`=lzma, `p`=lpaq). Works with every encryption mode.
- **Encode tab Compression segmented control** with five options (None / Auto / Deflate / LZMA / LPAQ). LPAQ disabled if no binary configured.
- **Settings tab**: LPAQ binary path with browse + auto-find buttons (auto-find scans common PEAzip install paths). New "Default compression" segmented.
- **`find_lpaq` API method** — returns the first LPAQ binary found in known PEAzip locations.
- **Compression info in info blurb** on Encode tab — explains overhead of each algorithm.
- **Decode auto-detect** — `peek_header` now detects and reports CV1 prefix; Decode tab surfaces "[Compressed: lzma]" in the detection card.
- Compression field stored in **key records** for redundancy (Key Vault decode can decompress even if CV1 prefix is missing).
- Help tab: new **Compression** section explaining when to use each algorithm.

### Changed
- `encode`, `encode_text`, `encode_keyvault` accept a `compression` parameter.
- `decode`, `decode_keyvault` automatically strip CV1 and decompress.

---

## [Unreleased — Key Vault Mode + Help] — 2026-05-16

### Added
- **Help tab** — 7th tab with curated explanations: 30-second overview, encryption modes table, header tiers table, fingerprint size trade-offs (8/2/0), Key Vault deep dive, alphabet picker guide, recovery scenarios, doomsday recovery notes. Buttons to open `docs/README.md` and `docs/ARCHITECTURE.md` in the OS default app.
- **Context-sensitive info blurb on Encode tab** — single card below the form that updates on every Header × Encryption change with a plain-English explanation of the trade-off you just picked. Warns to back up the key record whenever Key Vault is selected.
- **"Pick from Key Vault" button on Decode tab** — modal listing all stored key records; one click loads the alphabet, encoded string, and primes the Decode pipeline to use `decode_keyvault`.
- **Auto-route to KV decode** — when a file with `KV|` prefix is dropped, or when the pasted/loaded encoded string matches an existing record, the Decode tab automatically routes through `decode_keyvault` (no manual mode toggle needed).
- **KV banner on Decode tab** — green badge showing which key record is loaded; click ✕ to clear.
- **SHA-256 integrity result** — KV decode result shows ✓ or ✗ next to the byte count; mismatch displays an `INTEGRITY` red badge.
- **`open_path` API method** — opens any file with the OS default app (`os.startfile` on Windows, `xdg-open` elsewhere).
- **Key Vault encryption mode** — AES-256-CBC with salt/IV stored in a key record rather than embedded in the output. Zero crypto overhead in the tattoo string.
- **Three-tier header system** on Encode tab (replaces the SV1 checkbox + FpSize row):
  - **Bare** — no prefix, minimum output length
  - **Key ref** — `KV|XXXXXXXX|` (12 chars) linking to the key record for automatic decode
  - **Full SV1** — existing self-describing format with fingerprint and base number
- **`src/sv_kvcrypto.py`** — KV crypto engine: `kv_encrypt` / `kv_decrypt` using stdlib PBKDF2-SHA256 (100k iterations) + OpenSSL `-nosalt -K -iv` flags. Also generates doomsday `recovery.html`.
- **`src/sv_keyrecord.py`** — Key record CRUD: `save_record`, `list_records`, `get_record`, `delete_record`, `find_by_encoded_string`, `find_by_record_id_prefix`, `verify_integrity`, `export_record_card`.
- **`sv_key_records.json`** at project root — portable plain-JSON store (no OS lock-in). Passwords never stored here.
- **New API methods** in `sv_api.py`: `encode_keyvault`, `decode_keyvault`, `keyrecord_list`, `keyrecord_get`, `keyrecord_delete`, `keyrecord_export`, `keyrecord_find_by_string`.
- **Key Records section** in Vault tab — expandable cards showing label, alphabet, encryption mode, encoded string, SHA-256, and actions (Copy, Export card, Delete).
- **Export card** — writes a `.txt` recovery card + companion `recovery.html` (offline browser tool that derives AES key via Web Crypto API PBKDF2 and generates the exact OpenSSL command).
- **SHA-256 integrity check** — every KV decode verifies the decoded output against `original_sha256` stored in the key record. Mismatch surfaces as a warning.
- **Doomsday recovery path** — key record printout contains `salt_hex`, `iv_hex`, KDF parameters, and the exact OpenSSL command. `recovery.html` needs only a browser.

### Changed
- Encode tab: Encryption segmented now has four options (None / **Key Vault** / Salted / No-salt).
- Encode tab: Safety row replaced by Header tier segmented (Bare / Key ref / Full SV1) with Fingerprint size shown only for Full SV1.
- Vault tab: added third section "Key Vault records" spanning full width below the password/keycard grid.

---

## [Unreleased — GUI Beta] — 2026-05-15

### Added
- **Plain-text input mode on Encode tab** — `File | Text` source toggle; textarea with live UTF-8 byte counter; `encode_text` Python API method writes UTF-8 temp file, calls PowerShell, returns encoded string inline without leaving a permanent input file
- **`docs/` folder** — ARCHITECTURE.md, ROADMAP.md, CHANGELOG.md, README.md (moved from root)
- **`CLAUDE.md`** — developer guide with file index, invariants, key commands, documentation rules, and token efficiency guidelines

### Changed
- `docs/README.md` — updated to cover GUI workflow alongside legacy .bat workflow

---

## [GUI Alpha] — 2026-05-12 to 2026-05-15

### Added
- **Unified PyWebView GUI** (`sovereign_gui.py`, `Sovereign_GUI.bat`)
  - Single-window SPA with 6 tabs: Encode, Decode, Library, Editor, Vault, Settings
  - Dark theme CSS (`gui/css/sovereign.css`)
  - HTML5 drag-drop on Encode and Decode tabs
  - File browse dialogs via `pywebview.create_file_dialog`
  - Toast notification system
  - Confirm modal for destructive actions
  - Tab routing with `onShow` lifecycle hooks

- **Encode tab**
  - File mode: drag-drop zone + browse
  - Encryption segmented control: None / Salted AES-256 / No-salt AES-256
  - Password field with show/hide toggle + confirm field
  - Save password to keyring checkbox
  - Safety toggles: Self-describing header (SV1), Dual hex cross-verify
  - Fingerprint size segmented control: Full (8) / Short (2) / None
  - Live estimated character count
  - Result card: output path, char count, fingerprint, key card path, encoded text preview, Copy + Open Folder buttons

- **Decode tab**
  - SV1 header auto-detection on file load (`peek_header`)
  - Keyring password auto-fill
  - Manual alphabet + encryption override
  - Paste encoded text via collapsible `<details>` section
  - Try all alphabets fallback button
  - Decoded text preview (first 512 bytes if ASCII)

- **Library tab**
  - Full alphabet table (ID, name, base, fingerprint, engine, builtin/custom badge)
  - Import .svlib file dialog
  - Delete custom alphabet (with confirm modal)
  - Export key card (save dialog)
  - Open Editor button

- **Editor tab**
  - Embedded `alphabet_editor.html` in an iframe
  - Save to Library button calls `pywebview.api.save_alphabet` directly (no .svlib download needed)
  - Posts `alphabet-saved` message to parent — auto-refreshes Library tab and alphabet dropdowns

- **Vault tab**
  - Stored passwords: list entries (metadata only — hint, date), delete button
  - Key cards: browse configured vault folder for `.keycard.txt` files, click to preview

- **Settings tab**
  - Default alphabet, fingerprint size, salt mode, self-describing header defaults
  - Vault folder (key cards location)
  - OpenSSL path
  - Persisted to `sovereign_gui.cfg`

- **Python backend** (`src/`)
  - `sv_bridge.py` — subprocess wrapper around `sv_core.ps1`; `_parse_kv` output parser; `SovereignError` exception; library CRUD (pure Python)
  - `sv_keyring.py` — Windows Credential Manager integration; file-hash-based labels; `sv_keyring_index.json` metadata index
  - `sv_api.py` — `SovereignApi` class with full method surface

- **Project structure reorganization**
  - Python source modules moved from project root into `src/` subfolder
  - Path resolution updated to search `here` then `here.parent` for `sv_core.ps1`

### Fixed
- `SyntaxWarning: invalid escape sequence '\e'` in `sovereign_gui.py` docstring

---

## [FpSize / SV1 Variable Fingerprint] — 2026-05-12

### Added
- `-FpSize` parameter to `sv_core.ps1 -Mode Encode` — values: `0`, `2`, `8` (default `8`)
- Three SV1 header variants:
  - `SV1|fp:XXXXXXXX|b:NN|` — full 8-char fingerprint
  - `SV1|fp:XX|b:NN|` — short 2-char fingerprint (saves 6 chars)
  - `SV1|b:NN|` — base only, no fingerprint (saves 12 chars + `fp:` field)
- `[F]` toggle in `Sovereign_Encode.bat` cycles fingerprint size 8→2→0→8
- `Sovereign_Decode.bat` SV1 peek updated to handle variable-length fingerprints (regex `fp:[0-9a-f]{2,8}`) and base-only headers

### Changed
- Decode auto-match logic: short (2-char) fingerprints use prefix matching against full library fingerprints
- TryAll strip logic updated to handle all three header variants

---

## [Initial Release — Legacy CLI] — 2026-05-12

### Added
- `sv_core.ps1` — PowerShell encoding engine
  - Modes: `Encode`, `Decode`, `TryAll`, `ListLib`, `KeyCard`
  - AES-256 encryption via OpenSSL (salted and no-salt modes)
  - Bigint-engine encoders with sentinel byte (`0x01`) for leading-byte recovery
  - SHA-256 fingerprint per alphabet
  - Dual hex cross-verify
  - Key card generation
- `sv_lib.json` — built-in alphabets: hex (16), b32 (32), b37 (37), b40 (40), b48 (48), b52 (52), b58 (58), b64 (64), b85 (85)
- `Sovereign_Encode.bat` — interactive drag-drop encoder
- `Sovereign_Decode.bat` — interactive drag-drop decoder with TryAll
- `Sovereign_Config.bat` — library manager + OpenSSL path config
- `sv_import.bat` — `.svlib` importer
- `sovereign_alphabet_editor_v2.html` — visual alphabet builder (standalone, offline)
