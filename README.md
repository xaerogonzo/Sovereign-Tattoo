# Sovereign Tattoo

A Windows toolkit for encoding binary files into plain-text strings using custom character alphabets, with optional AES-256 encryption. Designed for permanent tattoo storage and general cryptographic archival.

**Full documentation is in [`docs/README.md`](docs/README.md).**

| Document | Contents |
|----------|---------|
| [`docs/README.md`](docs/README.md) | User guide — installation, workflows, recovery scenarios |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Technical design, module reference, data formats |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Feature status and future plans |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Change history |
| [`CLAUDE.md`](CLAUDE.md) | Developer guide for AI-assisted development |

## Quick Start

**GUI:**
```
pip install pywebview keyring
python sovereign_gui.py
```

**Legacy (no Python needed):**
Drag any file onto `Sovereign_Encode.bat` or `Sovereign_Decode.bat`.
