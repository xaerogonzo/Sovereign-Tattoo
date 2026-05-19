"""
Shared infrastructure for the SovereignApi mixins.

Includes:
  - Project root / settings persistence
  - Key Vault pipeline helpers (raise _KvError; orchestrators catch at the boundary)
  - Key-card file parsing
  - Misc utility helpers
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import sv_bridge
import sv_compress
import sv_keyring
import sv_keyrecord
import sv_kvcrypto


# ---------------------------------------------------------------------------
# Project root helper (handles src/ nesting)
# ---------------------------------------------------------------------------

# Single authoritative root resolver lives in sv_bridge — import it here so
# every storage module agrees on what "project root" means.
from sv_bridge import project_root as _project_root  # noqa: E402


# ---------------------------------------------------------------------------
# Settings persistence (separate from sovereign.cfg which is legacy)
# ---------------------------------------------------------------------------

def _settings_path() -> Path:
    return _project_root() / 'data' / 'sovereign_gui.cfg'


def _default_settings() -> dict[str, Any]:
    docs = Path(os.environ.get('USERPROFILE', str(Path.home()))) / 'Documents' / 'Sovereign' / 'KeyCards'
    return {
        'openssl_path': '',  # empty = assume on PATH
        'default_alphabet': 'b32',
        'default_fpsize': '8',
        'default_salt_mode': 'salt',
        'default_selfdesc': False,
        'default_compression': 'none',  # 'none'|'auto'|'zlib'|'lzma'|'lpaq'
        'lpaq_path': '',                 # deprecated; engines now live in bin/ via sv_engines
        'vault_folder': str(docs),
        'theme': 'system',
        'tesseract_path': '',            # empty = auto-detect (PATH + common install dirs)
    }


# Process-local cache: avoid re-reading data/sovereign_gui.cfg on every encode
# call. Invalidated automatically by _write_settings.
_settings_cache: dict[str, Any] | None = None


def _read_settings() -> dict[str, Any]:
    """Return current settings (cached after first read)."""
    global _settings_cache
    if _settings_cache is not None:
        # Return a copy so callers can't mutate the cache.
        return dict(_settings_cache)
    p = _settings_path()
    defaults = _default_settings()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            defaults.update(data)
        except Exception:
            pass
    _settings_cache = defaults
    return dict(defaults)


def _write_settings(s: dict[str, Any]) -> None:
    """Atomic write via .tmp + os.replace (see sv_keyrecord._write_store).

    Also refreshes the in-memory cache so the next _read_settings reflects
    the new on-disk state without a disk round-trip.
    """
    global _settings_cache
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(s, indent=2), encoding='utf-8')
    os.replace(tmp, p)
    _settings_cache = dict(s)


# ---------------------------------------------------------------------------
# Vault folder helpers (Phase B2 tattoo image storage)
# ---------------------------------------------------------------------------

def _tattoo_dirs() -> dict[str, Path]:
    """
    Return the tattoo subfolders under the user's configured vault folder.
    Creates them on first access.

      vault_root   — settings['vault_folder']
      images       — <vault>/tattoo_images   (reference photos)
      renders      — <vault>/tattoo_renders  (PNG/SVG exports)
    """
    settings = _read_settings()
    vault_root = Path(settings.get('vault_folder', '')).expanduser()
    if not vault_root or str(vault_root) in ('', '.'):
        vault_root = Path.home() / 'Documents' / 'Sovereign' / 'KeyCards'
    images = vault_root / 'tattoo_images'
    renders = vault_root / 'tattoo_renders'
    images.mkdir(parents=True, exist_ok=True)
    renders.mkdir(parents=True, exist_ok=True)
    return {'vault_root': vault_root, 'images': images, 'renders': renders}


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _safe_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the record safe to send to JS (no type issues)."""
    return {k: (v if v is not None else '') for k, v in record.items()}


def label_to_filename(label: str) -> str:
    """Convert a human label to a safe filename fragment."""
    s = re.sub(r'[^\w\s-]', '', label.lower())
    s = re.sub(r'[\s_]+', '_', s).strip('_')
    return s[:40] or 'record'


def _compress_to_tempfile(
    in_path: str,
    compression: str,
    lpaq_path: str,
) -> tuple[str, str, str]:
    """
    Read *in_path*, compress according to *compression* mode, write to a temp file.

    Returns (out_path, chosen_algo, cv1_prefix).
      - out_path: path to the compressed bytes (or in_path itself if no compression)
      - chosen_algo: the actually-applied algo (may be 'none' even if requested,
        if auto-mode found nothing better than the original)
      - cv1_prefix: the 'CV1|c:X|' string to prepend, or '' if no compression
    """
    if compression == sv_compress.ALGO_NONE or not compression:
        return (in_path, sv_compress.ALGO_NONE, '')

    try:
        raw = Path(in_path).read_bytes()
    except Exception as e:
        raise sv_compress.CompressError(f'Cannot read input for compression: {e}')

    if compression == 'auto':
        algo, compressed = sv_compress.auto_compress(raw, lpaq_path=lpaq_path)
    else:
        algo = compression
        compressed = sv_compress.compress_bytes(raw, algo, lpaq_path=lpaq_path)

    if algo == sv_compress.ALGO_NONE:
        return (in_path, sv_compress.ALGO_NONE, '')

    tmp = tempfile.NamedTemporaryFile(
        prefix='sv_compressed_', suffix='.bin', delete=False,
    )
    tmp.write(compressed)
    tmp.close()
    return (tmp.name, algo, sv_compress.build_cv1_header(algo))


# ---------------------------------------------------------------------------
# Key Vault pipeline helpers — raise _KvError so orchestrators stay thin
# ---------------------------------------------------------------------------

class _KvError(Exception):
    """Raised inside KV helpers; caught at encode_keyvault / decode_keyvault boundary."""
    pass


def _kv_resolve_input(text: str, in_path: str) -> tuple[str, str | None, str]:
    """
    Return (resolved_in_path, tmp_input_or_None, original_text).
    Raises _KvError on failure.
    """
    if text:
        try:
            tf = tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', suffix='.txt',
                prefix='sv_kvin_', delete=False,
            )
            tf.write(text)
            tf.close()
            return tf.name, tf.name, text
        except Exception as e:
            raise _KvError(f'Failed to write temp input: {e}')
    elif in_path:
        return in_path, None, ''
    else:
        raise _KvError('No source: provide in_path or text')


def _kv_hash_source(in_path: str) -> tuple[str, int]:
    """Return (sha256_hex, size_bytes). Raises _KvError on failure."""
    try:
        sha256 = sv_keyrecord.sha256_of_file(in_path)
        size = Path(in_path).stat().st_size
        return sha256, size
    except Exception as e:
        raise _KvError(f'Cannot read source file: {e}')


def _kv_encrypt_to_temp(
    kv_input: str, password: str, openssl_path: str,
) -> tuple[str, str, str]:
    """
    AES-256-CBC encrypt *kv_input* → fresh temp file.
    Returns (tmp_enc_path, salt_hex, iv_hex). Raises _KvError on failure.
    """
    tmp_enc = tempfile.mktemp(prefix='sv_kvenc_', suffix='.bin')
    try:
        salt_hex, iv_hex = sv_kvcrypto.kv_encrypt(kv_input, tmp_enc, password, openssl_path)
        return tmp_enc, salt_hex, iv_hex
    except sv_kvcrypto.KvCryptoError as e:
        raise _KvError(str(e))


def _kv_base_encode(
    tmp_enc: str, alph_id: str, selfdesc: bool, fpsize: str, dualverify: bool,
) -> tuple[str, dict[str, Any], str]:
    """
    Base-encode *tmp_enc* via sv_bridge.
    Returns (tmp_encoded_out_path, encode_result, encoded_raw_str).
    Raises _KvError on failure.
    """
    tmp_encoded_out = tmp_enc + f'.sv{alph_id}'
    encode_result = sv_bridge.encode(
        in_path=tmp_enc,
        out_path=tmp_encoded_out,
        alph_id=alph_id,
        password=None,
        salt_mode='salt',
        selfdesc=selfdesc,
        fpsize=fpsize,
        dualverify=dualverify,
    )
    if not encode_result.get('ok'):
        raise _KvError(encode_result.get('error', 'Base-encode failed'))
    try:
        encoded_raw = Path(tmp_encoded_out).read_text(encoding='utf-8', errors='replace').strip()
    except Exception as e:
        raise _KvError(f'Cannot read encoded output: {e}')
    return tmp_encoded_out, encode_result, encoded_raw


def _kv_build_tattoo_string(
    encoded_raw: str, header_mode: str, rec_id: str, cv1_prefix: str,
) -> str:
    """Assemble the final tattoo string with correct header layers."""
    if header_mode == 'keyref':
        encoded = f'KV|{rec_id}|{encoded_raw}'
    elif header_mode == 'bare':
        encoded = re.sub(r'^SV1\|[^|]*\|[^|]*\|', '', encoded_raw)
    else:  # fullsv1
        encoded = encoded_raw
    return cv1_prefix + encoded


def _kv_lookup_alphabet(alph_id: str) -> tuple[str, int, str, str]:
    """
    Return (name, base, fingerprint, chars) for *alph_id*.
    Falls back to safe defaults on any error (never raises).
    """
    try:
        lib_alphabets = sv_bridge.list_alphabets()
        a = next((x for x in lib_alphabets if x['id'] == alph_id), None)
        name = a['name'] if a else alph_id
        base = a['base'] if a else 0
        fp = a['fingerprint'] if a else ''
        lib_raw = json.loads(
            (sv_bridge.project_root() / 'sv_lib.json').read_text(encoding='utf-8')
        )
        a_full = next((x for x in lib_raw.get('alphabets', []) if x['id'] == alph_id), None)
        chars = a_full.get('chars', '') if a_full else ''
        return name, base, fp, chars
    except Exception:
        return alph_id, 0, '', ''


def _kv_get_encoded_string(params: dict[str, Any]) -> str:
    """Extract or read the encoded string from params. Raises _KvError on failure."""
    encoded = (params.get('encoded_string') or '').strip()
    if not encoded:
        in_path = params.get('in_path', '')
        if in_path:
            try:
                encoded = Path(in_path).read_text(encoding='utf-8', errors='replace').strip()
            except Exception as e:
                raise _KvError(f'Cannot read encoded file: {e}')
    if not encoded:
        raise _KvError('No encoded string provided')
    return encoded


def _kv_find_record(encoded_string: str, record_id: str) -> dict[str, Any]:
    """Locate the key record for *encoded_string*. Raises _KvError if not found."""
    record = None
    if record_id:
        record = sv_keyrecord.get_record(record_id)
    if record is None:
        record = sv_keyrecord.find_by_record_id_prefix(encoded_string)
    if record is None:
        record = sv_keyrecord.find_by_encoded_string(encoded_string)
    if record is None:
        raise _KvError('Key record not found. Check the Vault tab.')
    return record


def _kv_get_password(params: dict[str, Any], record: dict[str, Any]) -> str:
    """Get password from params or keyring. Raises _KvError if not found."""
    password = (params.get('password') or '').strip()
    if not password:
        try:
            stored = sv_keyring.get_password(record['id'])
            if stored:
                password = stored
        except Exception:
            pass
    if not password:
        raise _KvError('Password required (not found in keyring)')
    return password


def _kv_strip_headers(encoded_string: str, record: dict[str, Any]) -> tuple[str, str]:
    """
    Strip CV1, KV|, and SV1| header layers.
    Returns (raw_base_encoded, cv1_algo).
    """
    raw = encoded_string
    cv1_algo, raw = sv_compress.parse_cv1_header(raw)
    raw = re.sub(r'^KV\|[0-9a-f]{8}\|', '', raw)
    raw = re.sub(r'^SV1\|(?:fp:[0-9a-f]{2,8}\|)?b:\d+\|', '', raw).strip()
    if cv1_algo == sv_compress.ALGO_NONE:
        cv1_algo = record.get('compression', sv_compress.ALGO_NONE) or sv_compress.ALGO_NONE
    return raw, cv1_algo


def _kv_base_decode(raw_encoded: str, alph_id: str, tmp_txt: str, tmp_bin: str) -> None:
    """Write *raw_encoded* to *tmp_txt*, base-decode to *tmp_bin*. Raises _KvError on failure."""
    try:
        Path(tmp_txt).write_text(raw_encoded, encoding='utf-8')
    except Exception as e:
        raise _KvError(f'Cannot write temp encoded file: {e}')
    decode_result = sv_bridge.decode(
        in_path=tmp_txt,
        out_path=tmp_bin,
        alph_id=alph_id,
        password=None,
        salt_mode='salt',
    )
    if not decode_result.get('ok'):
        raise _KvError(f"Base decode failed: {decode_result.get('error', '')}")


def _kv_decrypt(
    tmp_bin: str, password: str, salt_hex: str, iv_hex: str,
    openssl_path: str, tmp_decrypted: str,
) -> None:
    """KV-decrypt *tmp_bin* → *tmp_decrypted*. Raises _KvError on failure."""
    try:
        sv_kvcrypto.kv_decrypt(tmp_bin, tmp_decrypted, password, salt_hex, iv_hex, openssl_path)
    except sv_kvcrypto.KvCryptoError as e:
        raise _KvError(str(e))


def _kv_decompress_or_move(
    tmp_decrypted: str, cv1_algo: str, out_path: str, lpaq_path: str,
) -> None:
    """Move or decompress *tmp_decrypted* → *out_path*. Raises _KvError on failure."""
    if cv1_algo != sv_compress.ALGO_NONE:
        try:
            compressed = Path(tmp_decrypted).read_bytes()
            plain = sv_compress.decompress_bytes(compressed, cv1_algo, lpaq_path=lpaq_path)
            Path(out_path).write_bytes(plain)
        except sv_compress.CompressError as e:
            raise _KvError(f'Decompression failed: {e}')
    else:
        shutil.move(tmp_decrypted, out_path)


def _kv_text_preview(out_path: str) -> str:
    """Return a short UTF-8 text preview of *out_path* (empty string on binary/error)."""
    try:
        raw = Path(out_path).read_bytes()[:512]
        return raw.decode('utf-8')
    except Exception:
        return ''


# ---------------------------------------------------------------------------
# Key-card file parsing (for Vault tab)
# ---------------------------------------------------------------------------

_KEYCARD_FIELD_RE = re.compile(r'^(Alphabet|ID|Base|Fingerprint|Engine|Generated)\s*:\s*(.+?)\s*$')


def _parse_keycard(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {'path': str(path), 'name': path.name}
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return info
    for line in text.splitlines()[:30]:  # header is at top
        m = _KEYCARD_FIELD_RE.match(line)
        if m:
            key = m.group(1).lower()
            info[key] = m.group(2).split('  ')[0].strip()
    info['modified'] = time.strftime('%Y-%m-%d %H:%M', time.localtime(path.stat().st_mtime))
    return info
