"""
sv_keyrecord.py - Key record CRUD for the Key Vault mode

Key records are stored in sv_key_records.json at the project root.
The file is plain JSON — portable, no host lock-in.
Passwords are NEVER stored in this file.

Schema for one record:
{
  "id":                  "a3f2b1c8",       # 8 hex chars, unique
  "created":             "2026-05-16 14:30:00",
  "label":               "left forearm",   # user-supplied, optional
  "header_mode":         "bare"|"keyref"|"fullsv1",
  "alphabet_id":         "b32",
  "alphabet_name":       "Base 32",
  "alphabet_fingerprint":"dab1d0de",
  "alphabet_chars":      "ABCDEFGHIJ...",  # full char string — sufficient for recovery
  "base":                32,
  "encryption":          "aes256cbc-kv",   # or "none"
  "salt_hex":            "...",            # present for kv-encrypted records
  "iv_hex":              "...",
  "kdf":                 "pbkdf2-sha256",
  "kdf_iterations":      100000,
  "original_text":       "...",            # optional, only if user opted in
  "original_size_bytes": 50,
  "original_sha256":     "...",
  "encoded_string":      "KV|a3f2b1c8|...",  # full tattoo string with any prefix
  "char_count":          92,
  "source":              "text"|"file",
  "openssl_cli":         "openssl aes-256-cbc -d -nosalt ..."
}
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Storage location
# ---------------------------------------------------------------------------

# Single authoritative root resolver lives in sv_bridge — import it here so
# every storage module agrees on what "project root" means.
from sv_bridge import project_root as _project_root  # noqa: E402


def _records_path() -> Path:
    return _project_root() / 'data' / 'sv_key_records.json'


# ---------------------------------------------------------------------------
# Raw read / write
# ---------------------------------------------------------------------------

def _read_store() -> dict[str, Any]:
    p = _records_path()
    if not p.exists():
        return {'records': {}}
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        if 'records' not in data:
            data['records'] = {}
        return data
    except Exception:
        return {'records': {}}


def _write_store(store: dict[str, Any]) -> None:
    """Atomic write: serialise to a sibling .tmp file then os.replace().

    os.replace is atomic on both POSIX and Windows (Python 3.3+) — the
    target file is either the old contents or the new contents, never a
    half-written truncation.
    """
    p = _records_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Public CRUD API
# ---------------------------------------------------------------------------

def generate_id() -> str:
    """Return a fresh 8-hex-char unique record ID."""
    return secrets.token_hex(4)   # 4 bytes = 8 hex chars


def save_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Save *record* to the store.  If a record with the same id already exists
    it is replaced.  Returns the saved record.
    """
    if 'id' not in record:
        record = dict(record)
        record['id'] = generate_id()
    if 'created' not in record:
        record['created'] = time.strftime('%Y-%m-%d %H:%M:%S')

    store = _read_store()
    store['records'][record['id']] = record
    _write_store(store)
    return record


def list_records() -> list[dict[str, Any]]:
    """Return all key records, newest first."""
    store = _read_store()
    records = list(store['records'].values())
    records.sort(key=lambda r: r.get('created', ''), reverse=True)
    return records


def get_record(record_id: str) -> dict[str, Any] | None:
    """Return the record with *record_id*, or None."""
    store = _read_store()
    return store['records'].get(record_id)


def delete_record(record_id: str) -> bool:
    """Delete the record with *record_id*.  Returns True if it existed."""
    store = _read_store()
    if record_id not in store['records']:
        return False
    del store['records'][record_id]
    _write_store(store)
    return True


def find_by_encoded_string(encoded_string: str) -> dict[str, Any] | None:
    """
    Search for a record whose stored encoded_string matches *encoded_string*.
    Strips leading/trailing whitespace before comparing.
    Returns the first match, or None.
    """
    needle = encoded_string.strip()
    if not needle:
        return None
    for record in list_records():
        stored = (record.get('encoded_string') or '').strip()
        if stored and stored == needle:
            return record
    return None


def find_by_record_id_prefix(encoded_string: str) -> dict[str, Any] | None:
    """
    If *encoded_string* starts with the KV| header, extract the record ID
    and look it up directly.  Returns the record or None.
    """
    import re
    m = re.match(r'^KV\|([0-9a-f]{8})\|', encoded_string.strip())
    if not m:
        return None
    return get_record(m.group(1))


# ---------------------------------------------------------------------------
# Integrity helper
# ---------------------------------------------------------------------------

def sha256_of_file(path: str) -> str:
    """Return lowercase hex SHA-256 of the file at *path*."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_text(text: str) -> str:
    return sha256_of_bytes(text.encode('utf-8'))


def verify_integrity(record: dict[str, Any], decoded_path: str) -> bool | None:
    """
    Compare SHA-256 of the decoded file against record['original_sha256'].
    Returns True (match), False (mismatch), or None (no stored hash).
    """
    expected = record.get('original_sha256')
    if not expected:
        return None
    try:
        actual = sha256_of_file(decoded_path)
        return actual.lower() == expected.lower()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Export: printable card + recovery.html
# ---------------------------------------------------------------------------

def export_record_card(record: dict[str, Any], out_path: str) -> dict[str, str]:
    """
    Write a human-readable recovery card to *out_path* (.txt).
    Also writes a companion *recovery.html* to the same directory.
    Returns {'card_path': ..., 'html_path': ...}.
    """
    import sv_kvcrypto as _kv

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # ---- Build card text ----
    label      = record.get('label') or '(none)'
    rec_id     = record.get('id', '')
    created    = record.get('created', '')
    header_mode= record.get('header_mode', '')
    alph_name  = record.get('alphabet_name', '')
    alph_id    = record.get('alphabet_id', '')
    base       = record.get('base', '')
    fp         = record.get('alphabet_fingerprint', '')
    alph_chars = record.get('alphabet_chars', '')
    enc        = record.get('encryption', '')
    salt_hex   = record.get('salt_hex', '')
    iv_hex     = record.get('iv_hex', '')
    kdf        = record.get('kdf', '')
    iterations = record.get('kdf_iterations', '')
    orig_sha   = record.get('original_sha256', '')
    orig_bytes = record.get('original_size_bytes', '')
    char_count = record.get('char_count', '')
    encoded    = record.get('encoded_string', '')
    source     = record.get('source', '')
    openssl_cli= record.get('openssl_cli', '')

    lines = [
        'SOVEREIGN KEY VAULT RECORD',
        '=' * 60,
        f'Label          : {label}',
        f'Record ID      : {rec_id}',
        f'Created        : {created}',
        f'Source         : {source}',
        '',
        '--- Alphabet ---',
        f'ID             : {alph_id}',
        f'Name           : {alph_name}',
        f'Base           : {base}',
        f'Fingerprint    : {fp}',
        f'Characters     : {alph_chars}',
        '',
        '--- Header / Encoding ---',
        f'Header mode    : {header_mode}',
        f'Encoded chars  : {char_count}',
        '',
        '--- Encryption ---',
        f'Mode           : {enc}',
    ]
    if salt_hex:
        lines += [
            f'KDF            : {kdf}',
            f'KDF iterations : {iterations}',
            f'Salt (hex)     : {salt_hex}',
            f'IV (hex)       : {iv_hex}',
        ]
    if orig_sha:
        lines += [
            '',
            '--- Integrity ---',
            f'SHA-256        : {orig_sha}',
            f'Size (bytes)   : {orig_bytes}',
        ]
    if encoded:
        lines += [
            '',
            '--- Encoded string (copy exactly) ---',
            encoded,
        ]
    if openssl_cli:
        lines += [
            '',
            '--- Manual recovery (OpenSSL) ---',
            openssl_cli,
            '',
            'Steps:',
            '1. Decode the encoded string back to binary using Sovereign or',
            '   any base-N decoder with the alphabet characters above.',
            '   Save as: encrypted.bin',
            '2. Derive AES key:',
            '   PBKDF2-HMAC-SHA256(password.utf8, bytes.fromhex(salt_hex), iterations, 32)',
            '3. Run the OpenSSL command above, filling in the derived key.',
            '4. Alternatively, open recovery.html in a browser — it does',
            '   step 2 automatically using the browser\'s Web Crypto API.',
        ]
    lines += [
        '',
        '=' * 60,
        'Store this card with medical records, estate documents, or a safety deposit box.',
    ]

    card_text = '\n'.join(lines) + '\n'
    out.write_text(card_text, encoding='utf-8')

    # ---- Recovery HTML ----
    html_path = out.with_suffix('').with_suffix('.recovery.html')
    try:
        html_content = _kv.build_recovery_html(record)
        html_path.write_text(html_content, encoding='utf-8')
    except Exception:
        html_path = None  # type: ignore

    return {
        'card_path': str(out),
        'html_path': str(html_path) if html_path else '',
    }


# ---------------------------------------------------------------------------
# Build the openssl_cli hint stored on every KV record
# ---------------------------------------------------------------------------

def build_openssl_cli_hint(iv_hex: str) -> str:
    return (
        'openssl aes-256-cbc -d -nosalt \\\n'
        f'    -K <derive: PBKDF2-HMAC-SHA256(password, salt_hex, iterations, 32)> \\\n'
        f'    -iv {iv_hex} \\\n'
        '    -in encrypted.bin -out recovered_file'
    )
