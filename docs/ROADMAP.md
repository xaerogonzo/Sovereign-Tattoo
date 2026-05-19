# Roadmap — Sovereign Tattoo

## Current Version: GUI Beta

---

## Phase Status

### ✅ Phase 1 — PowerShell Engine (Complete)
- `sv_core.ps1` — Encode, Decode, TryAll, ListLib, KeyCard modes
- AES-256 encryption (salted and no-salt via OpenSSL)
- Custom alphabet library (`sv_lib.json`)
- SHA-256 fingerprint for alphabet identification
- Dual hex cross-verify safety mode

### ✅ Phase 2 — Legacy CLI Interface (Complete)
- `Sovereign_Encode.bat` — drag-drop encoder with menu
- `Sovereign_Decode.bat` — drag-drop decoder with auto-detect
- `Sovereign_Config.bat` — library/config manager
- `sv_import.bat` — .svlib importer

### ✅ Phase 3 — SV1 Self-Describing Header + FpSize (Complete)
- `SV1|fp:XXXXXXXX|b:NN|` header format
- Variable fingerprint length: Full (8), Short (2), None (0)
- Decode auto-detects variable-length fingerprints and base-only headers
- `[F]` toggle in legacy encoder cycles 8→2→0

### ✅ Phase 4 — Unified PyWebView GUI (Complete)
Core GUI built and smoke-tested:
- **Encode tab** — File mode (drag-drop/browse) + Text mode (paste/type), all encoding options
- **Decode tab** — SV1 header auto-detect, keyring auto-fill, TryAll button
- **Library tab** — full alphabet table, import .svlib, delete custom, export key card
- **Editor tab** — embedded alphabet builder (calls `save_alphabet` API directly)
- **Vault tab** — stored passwords (metadata only) + key card file browser
- **Settings tab** — defaults, vault folder, OpenSSL path

### ✅ Phase 5 — Python Backend (Complete)
- `src/sv_bridge.py` — PowerShell subprocess wrapper
- `src/sv_keyring.py` — Windows Credential Manager integration
- `src/sv_api.py` — full JS-facing API (encode, decode, tryall, vault, settings, file dialogs)
- `sovereign_gui.py` — entry point with drag-drop file routing

### ✅ Phase 6 — Project Structure (Complete)
- Python source moved to `src/` subfolder
- Documentation suite in `docs/`
- `CLAUDE.md` developer guide at root

---

## ✅ Phase 7 — Key Vault Mode (Complete)

Three-tier header system (Bare / Key ref / Full SV1) × four encryption modes (None / Key Vault / Salted / No-salt):

- `src/sv_kvcrypto.py` — PBKDF2-SHA256 (100k iter) + OpenSSL `-nosalt -K -iv`; `recovery.html` generator
- `src/sv_keyrecord.py` — portable JSON record store, integrity verification, export (card + recovery.html)
- New API methods: `encode_keyvault`, `decode_keyvault`, `keyrecord_list/get/delete/export/find_by_string`
- Encode tab: header tier segmented replaces SV1 checkbox; 4th encryption option (Key Vault)
- Vault tab: Key Records section with expandable cards, copy, export, delete

---

## Phase 8 — Bug Testing & Polish (In Progress)

### Known Issues / To Investigate
- [ ] KV round-trip smoke test: Bare+KV, Key-ref+KV
- [ ] SHA-256 integrity warning visible in Decode result (decode_keyvault result surfaces integrity_ok)
- [ ] Custom and non-standard alphabet round-trip testing (b37, b40, b48, b52, b58, b85)
- [ ] Edge cases: empty file, very large file, non-ASCII filenames
- [ ] Drag-drop from File Explorer into GUI text mode textarea
- [ ] Key card export from Library tab — verify file dialog + output

### Polish Items
- [ ] DevTools panel auto-opens on launch (expected — `debug=True` in sovereign_gui.py; close manually or set to `False` for release)
- [ ] Error toasts for PowerShell not on PATH
- [ ] Improve "Open folder" for text-mode encode (currently hidden; could open temp folder)
- [ ] Decode tab: detect `KV|` prefix in pasted text and auto-lookup key record

---

## Phase 8 — Packaging (Deferred)
Single `.exe` distribution via PyInstaller.

- [ ] `sovereign_gui.spec` — bundle `sv_core.ps1`, `sv_lib.json`, `gui/` as data files
- [ ] Verify on clean Windows VM (only OpenSSL installed)
- [ ] Target: under 50 MB
- [ ] Auto-detect bundled vs development mode in path resolution

---

## Future Directions

These are exploratory — not committed, not scheduled.

### GPG / Public-Key Encryption Layer
- `Sovereign_Sign.bat` / `Sovereign_Verify.bat`
- Chain: `file → GPG encrypt → sv_core.ps1 encode`
- No key management in Sovereign — use Kleopatra / existing GPG setup
- Tattoo impact: optional pre-encryption step before base encoding

### Steganography Mode
- Embed encoded text inside an image or audio file
- Recovery: extract steganographic payload, then decode normally
- Use case: deniable storage

### Cross-Platform Port
- PowerShell Core runs on Linux/macOS
- PyWebView runs cross-platform
- Main blocker: `keyring` backend differs per OS; path handling; OpenSSL availability
- Low priority — primary use case is Windows tattoo workflow

### Language Translations
- UI strings extracted to JSON locale files
- Keep PowerShell engine language-agnostic (already is)

### Mobile Companion
- Read-only: scan QR code containing SV1-encoded data, decode with known alphabet
- Stretch goal — entirely separate project

---

## Architecture Philosophy (Stable)

- **Modular** — new features don't touch the main tattoo pipeline
- **Minimal dependencies** — use external CLI tools (OpenSSL, GnuPG) rather than embedding them
- **Offline-first** — no network calls, no key servers, no telemetry
- **Recoverable** — every encryption method must support recovery from encoded text alone
- **Legibility-first** — tattoo output prioritizes readability on aged skin over density
