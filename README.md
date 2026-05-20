# Sovereign Tattoo

> **Encode any secret into text. Wear it forever.**

Sovereign Tattoo is a Windows app for encoding files and text into compact,
human-readable strings using custom character alphabets — then tattooing the
result on your skin as permanent, unloseable cold storage.

The encoded string carries your data. The tattoo carries the string. No cloud,
no hard drive, no password manager required.

---

## What it does

| | |
|---|---|
| **Encode** | Any file or text → compact encoded string (Base 32 to Base 85) |
| **Encrypt** | Optional AES-256-CBC before encoding. Key record stored separately, never in the string. |
| **Compress** | Optional zlib / LZMA / PAQ compression before encrypt → shorter tattoo |
| **Tattoo Studio** | 40+ layouts (spiral, circle, wave, star, DNA helix, heart…) with live canvas preview and SVG/PNG export |
| **My Tattoos** | Personal dossier — track every tattoo: placement, artist, studio, healing status, photos |
| **AI Analysis** | Upload a tattoo photo → ask Claude Vision for design suggestions, style advice, or cover-up options |
| **Decode** | Paste or scan any encoded string back to the original file, anywhere |
| **Key Vault** | Cold-storage key records with offline recovery HTML — decrypt without the app if needed |

---

## Why tattoo storage?

- A tattoo cannot be stolen, lost in a fire, or forgotten in a drawer
- A well-chosen alphabet (Base 32, all-caps + digits) remains legible as ink ages
- The encoded string is just text — it can be decoded with any implementation of the algorithm
- The included recovery HTML lets you decrypt your data with just a browser and OpenSSL, no app required

Sovereign also works as a general cryptographic archival tool — the tattoo use
case is the extreme end of the durability spectrum.

---

## Quick start

**Requirements:** Windows 10/11, Python 3.10+, PowerShell 5.1 (built in)

```
pip install -r requirements.txt
python sovereign_gui.py
```

Or double-click **`Sovereign_GUI.bat`**.

For AES-256 encryption, [OpenSSL](https://slproweb.com/products/Win32OpenSSL.html)
must be on your PATH (or set the path in Settings).

---

## The GUI

Seven tabs, one window:

| Tab | Purpose |
|-----|---------|
| **Encode** | File or text → encoded string. All options in one place. |
| **Decode** | Encoded string or file → original. Auto-detects alphabet. |
| **Library** | Browse, import, and delete alphabets. Export printable key cards. |
| **Editor** | Visual alphabet designer — build custom character sets. |
| **Vault** | Manage Key Vault records and stored passwords (Windows Credential Manager). |
| **Tattoo** | Layout Studio · My Tattoos · Body Map |
| **Settings** | Defaults, paths, compression engines, AI (Claude Vision) API key. |

### Tattoo tab

**Layout Studio** — choose from 40+ layouts, tune the parameters, preview on
canvas, export as SVG or PNG ready to hand to your artist.

**My Tattoos** — a personal dossier for every tattoo you have or plan. Track
placement, artist, studio, style, healing status, ink colors, price, and photos.
Encoded tattoos link directly to their Key Vault record.

**Body Map** — visual silhouette showing which zones have tattoos. Click a zone
to filter the My Tattoos grid.

---

## Built-in alphabets

| ID | Base | Notes |
|----|------|-------|
| `b37` | 37 | No ambiguous chars (no 0/O, 1/I). **Best for tattoos.** |
| `b32` | 32 | RFC 4648 uppercase. Legible as ink ages. |
| `hex` | 16 | Universally recoverable without any tools. |
| `b58` | 58 | Bitcoin-style, no ambiguous chars. |
| `b64` | 64 | RFC 4648 standard. |
| `b85` | 85 | High-density. Not tattoo-friendly (special chars). |

Custom alphabets can be created in the Editor tab and exported as `.svlib` files.

---

## Recovery (no app required)

Every Key Vault record exports a self-contained `recovery.html`. Open it in any
browser, enter your password, and it derives the AES key using the browser's
native Web Crypto API and shows the exact OpenSSL command to decrypt your data.

```
openssl aes-256-cbc -d -nosalt -K <derived_key> -iv <iv_from_record> \
    -in encoded_decoded.bin -out recovered_file
```

---

## Optional features

| Feature | Setup |
|---------|-------|
| **AI tattoo analysis** (Claude Vision) | Add an Anthropic API key in Settings → AI Features |
| **OCR** (scan encoded strings from photos) | Install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki), set path in Settings |
| **PAQ / LPAQ8 compression** | Drop `lpaq8.exe` or `paq8o.exe` into `bin/` |

---

## Documentation

| Doc | Contents |
|-----|---------|
| [`docs/README.md`](docs/README.md) | Full user guide — installation, workflows, recovery |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Technical design, module reference, data formats |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Feature status and planned work |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Change history |

---

## Building a standalone .exe

```
pip install nuitka ordered-set zstandard
python scripts/build.py
```

Output lands in `dist/sovereign_gui.dist/sovereign_gui.exe` — no Python install
required on the target machine.

---

*Sovereign Tattoo — your data, in your skin.*
