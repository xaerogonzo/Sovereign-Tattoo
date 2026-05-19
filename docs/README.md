# Sovereign Tattoo Encoding System

A Windows toolkit for encoding any binary file into a plain-text string using a custom character alphabet, with optional AES-256 encryption. Designed for the use case of permanently storing encoded data as a tattoo — where the only recovery material may be text on human skin.

Also useful as a general-purpose archival encoding tool.

---

## Requirements

- Windows 10/11
- PowerShell 5.1+ (built into Windows)
- Python 3.10+ with `pywebview` and `keyring` — for the GUI only
  ```
  pip install pywebview keyring
  ```
- [OpenSSL](https://slproweb.com/products/Win32OpenSSL.html) on PATH — for AES-256 encryption only

---

## Two Ways to Use It

### Option A — Unified GUI (Recommended)

Double-click **`Sovereign_GUI.bat`** or run:
```
python sovereign_gui.py
```

The GUI provides a single window with six tabs:

| Tab | What it does |
|-----|-------------|
| **Encode** | File or plain-text → encoded string. All options in one place. |
| **Decode** | Encoded file or pasted text → original file. Auto-detects alphabet. |
| **Library** | Browse, import, and delete alphabets. Export key cards. |
| **Editor** | Visual alphabet builder — design custom alphabets, save directly to library. |
| **Vault** | Manage stored passwords (Windows Credential Manager) and key card files. |
| **Settings** | Default alphabet, encryption mode, key card folder, OpenSSL path. |

You can also drag an encoded file directly onto `Sovereign_GUI.bat` — it opens on the Decode tab with the file pre-loaded.

---

### Option B — Legacy .bat Files

Four separate drag-drop launchers. Fully functional without Python installed.

| File | Purpose |
|------|---------|
| `Sovereign_Encode.bat` | Drag any file onto this to encode it |
| `Sovereign_Decode.bat` | Drag an encoded file onto this to decode it |
| `Sovereign_Config.bat` | Configure OpenSSL path and manage the alphabet library |
| `sv_import.bat` | Drag a `.svlib` file onto this to add it to the library |

---

## Built-in Alphabets

| ID | Name | Base | Notes |
|----|------|------|-------|
| `hex` | Hex | 16 | Standard hexadecimal. Universally recoverable without any tools. |
| `b32` | Base 32 | 32 | RFC 4648. Uppercase only. Good tattoo choice. |
| `b37` | b37 Tattoo Safe | 37 | No ambiguous chars (no 0/O, no 1/I). **Best for tattoos.** |
| `b40` | Base 40 | 40 | Alphanumeric + basic symbols. |
| `b48` | Base 48 | 48 | Extended alphanumeric. |
| `b52` | Base 52 | 52 | Mixed-case letters only. |
| `b58` | Base 58 | 58 | Bitcoin-style. No ambiguous chars. |
| `b64` | Base 64 | 64 | RFC 4648. Industry standard. |
| `b85` | Base 85 | 85 | High-density. Not tattoo-friendly (special chars). |

For tattoos, use **`b37`** (unambiguous characters) or **`b32`** (all-caps + digits — legible even as ink fades).

---

## Encoding Options

### Encryption
| Mode | Description |
|------|-------------|
| **None** | Raw base encoding — no password, no encryption |
| **Salted AES-256** | OpenSSL AES-256-CBC with salt header (recommended) |
| **No-salt AES-256** | Deterministic output — same input + password → same output |

### Self-Describing Header (SV1)
Prepends a recovery header to the encoded output:
```
SV1|fp:4bf5122f|b:32|JBSWY3DPEB...
```
The decoder reads this and auto-selects the correct alphabet. **Enable this for tattoos** — it makes the encoded string self-sufficient even if the file extension is lost.

### Fingerprint Size
When the SV1 header is on, choose how much of the alphabet fingerprint to include:
- **Full (8)** — 8 hex chars, unambiguous identification
- **Short (2)** — 2 hex chars, saves 6 characters in the output
- **None** — base number only, saves maximum characters

### Dual Hex Cross-Verify
After encoding, independently re-encodes with hex, decodes both results, and byte-compares them. Shows `[DUAL-VERIFIED]` before accepting the output. Use for tattoo encodes where you want certainty the alphabet is lossless.

---

## Output Filename Convention

| Mode | Extension |
|------|-----------|
| Unencrypted | `filename.ext.b32` (e.g. `document.pdf.b32`) |
| Encrypted | `filename.ext.svb32` (e.g. `document.pdf.svb32`) |
| Key card | `filename.ext.b32.keycard.txt` |

---

## Custom Alphabets

### Building a Custom Alphabet (GUI)

1. Open the **Editor** tab.
2. Click characters to toggle them on/off. Orange dots indicate legibility risk for tattoos.
3. Use the Compare tab to see output size versus built-ins.
4. Click **Save to Library** — the alphabet is immediately available in Encode/Decode.

### Building a Custom Alphabet (Legacy)

1. Open `sovereign_alphabet_editor_v2.html` in any browser.
2. Design your alphabet.
3. Export → **Download .svlib**.
4. Drag the `.svlib` file onto `sv_import.bat`.

### Managing Alphabets

- **GUI:** Library tab — lists all alphabets, import .svlib, delete custom, export key card.
- **Legacy:** `Sovereign_Config.bat` → `[6] Manage alphabet library`.

---

## Safety Features

Because a tattoo cannot be un-inked, several redundant recovery mechanisms are built in:

### 1. Fingerprint in header
Every encode can include a SHA-256-based fingerprint identifying the alphabet used:
```
SV1|fp:4bf5122f|b:43|ACTUALENCODEDDATA...
```
The `fp:` value lets you identify which alphabet was used even if all other context is lost.

### 2. Key card
A `.keycard.txt` recovery file is generated alongside every custom-alphabet encode:
```
SOVEREIGN KEY CARD
==================
Generated  : 2026-05-12 14:30
Alphabet   : My Tattoo b43
Fingerprint: 4bf5122f
Characters : ABCDEFGH...
Test vector:
  Input (hex): 01 02 03 04 05 06 07 08
  Encoded    : XKJMQRAB...
  Decode back: 01 02 03 04 05 06 07 08  PASS
```
The Characters string alone is sufficient to reconstruct the alphabet. **Store with medical records or estate documents.**

### 3. SV1 self-describing header
Toggle on to embed the fingerprint and base number directly in the encoded string. The decoder reads it and auto-selects the correct alphabet.

### 4. Dual hex cross-verify
Independent round-trip check before output is accepted. Confirms the custom alphabet is lossless.

---

## Recovery Scenarios

### Scenario A — Built-in alphabet, no header
1. Save the encoded text to a `.txt` file.
2. Open the **Decode** tab (or drag onto `Sovereign_Decode.bat`).
3. Click **Try all alphabets** — brute-forces every built-in and writes each decoded candidate.
4. The correct output will have the expected byte count and open in its application.

### Scenario B — Custom alphabet with SV1 header
1. The text starts with `SV1|fp:XXXXXXXX|b:NN|` — note the fingerprint.
2. Match the fingerprint to a saved key card to retrieve the character string.
3. Open the Editor tab (or `sovereign_alphabet_editor_v2.html`), build the alphabet, save to library.
4. Drag the encoded file into Decode — it auto-detects the alphabet.

### Scenario C — Custom alphabet, no header, key card exists
1. Open Editor, enter the characters listed on the key card, save to library.
2. Decode the file — select the imported alphabet manually.

### Scenario D — Custom alphabet, no header, no key card
> **This is unrecoverable.** Without the exact character string and its ordering, the data cannot be decoded.

---

## What to Back Up

> **If you use a custom alphabet for a tattoo, losing these backups means losing the data permanently.**

| Item | What it is | Where to keep it |
|------|------------|-----------------|
| Key card `.txt` | Full character string + test vector | Print and store with medical records, estate documents, or a safety deposit box |
| `.svlib` file | JSON export of the alphabet | USB drive + email to yourself |
| `sv_lib.json` | Full library backup | Keep alongside the `.svlib` backup |

For built-in alphabets (`hex`, `b32`, `b37`, etc.), no backup is needed — brute-force with Try All.

---

## Technical Notes

- All encoding is local — no internet connection is ever used.
- The `.svlib` format is plain JSON and is human-readable as a backup.
- Encoded output is plain ASCII text — can be stored in any medium: file, clipboard, print, tattoo, QR code.
- `sovereign_gui.cfg` is auto-created on first Settings save.
- For technical architecture details, see `docs/ARCHITECTURE.md`.
