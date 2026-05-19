"""DecodeApiMixin — file decode, TryAll brute-force, header peek, and KV decode."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import sv_bridge
import sv_compress
import sv_keyring
import sv_keyrecord

from ._helpers import (
    _KvError,
    _kv_base_decode,
    _kv_decompress_or_move,
    _kv_decrypt,
    _kv_find_record,
    _kv_get_encoded_string,
    _kv_get_password,
    _kv_strip_headers,
    _kv_text_preview,
    _read_settings,
    _safe_record,
    label_to_filename,
)


# ---------------------------------------------------------------------------
# decode() helpers — each handles one responsibility
# ---------------------------------------------------------------------------

def _decode_resolve_out_path(in_path: str, out_path: str | None) -> str:
    """Return out_path if given; otherwise strip the last extension from in_path.

    Handles double-extension filenames (e.g. photo.jpg.b32 → photo.jpg).
    """
    if out_path:
        return out_path
    p = Path(in_path)
    result = str(p.with_suffix(''))
    # Second strip for double-extension edge case (e.g. .b32.b32)
    if result.endswith(p.suffix) and p.suffix:
        result = result[: -len(p.suffix)]
    return result


def _decode_lookup_password(in_path: str, password: str | None) -> str | None:
    """Return *password* if already supplied; otherwise attempt a keyring look-up."""
    if password:
        return password
    try:
        label = sv_keyring.file_label(in_path)
        return sv_keyring.get_password(label) or None
    except Exception:
        return None


def _decode_strip_cv1(in_path: str) -> tuple[str, str, str | None]:
    """Detect and strip a CV1 compression header from *in_path*.

    Returns ``(decode_input, cv1_algo, temp_path)``.
    *temp_path* is non-None only when a CV1 header was found and the stripped
    content was written to a temporary file; the caller must delete it.
    """
    try:
        raw = Path(in_path).read_text(encoding='utf-8', errors='replace').strip()
        cv1_algo, stripped = sv_compress.parse_cv1_header(raw)
        if cv1_algo != sv_compress.ALGO_NONE:
            tf = tempfile.NamedTemporaryFile(
                prefix='sv_cv1_strip_', suffix='.txt',
                mode='w', encoding='utf-8', delete=False,
            )
            tf.write(stripped)
            tf.close()
            return tf.name, cv1_algo, tf.name
    except Exception:
        pass
    return in_path, sv_compress.ALGO_NONE, None


def _decode_and_decompress(
    decode_in: str,
    out_path: str,
    cv1_algo: str,
    alph_id: str | None,
    password: str | None,
    salt_mode: str,
    lpaq_path: str,
) -> dict[str, Any]:
    """Run ``sv_bridge.decode`` then optionally decompress a CV1-wrapped payload.

    Uses a temporary intermediate file when decompression is needed so that
    *out_path* only receives the final, fully-decoded bytes. The intermediate
    is always cleaned up — even when ``sv_bridge.decode`` fails after writing
    a partial file.
    """
    needs_decompress = cv1_algo != sv_compress.ALGO_NONE
    intermediate = (
        tempfile.mktemp(prefix='sv_pre_decompress_', suffix='.bin')
        if needs_decompress else out_path
    )

    try:
        result = sv_bridge.decode(
            in_path=decode_in,
            out_path=intermediate,
            alph_id=alph_id,
            password=password,
            salt_mode=salt_mode,
        )
        if not result.get('ok') or not needs_decompress:
            return result

        try:
            compressed   = Path(intermediate).read_bytes()
            decompressed = sv_compress.decompress_bytes(compressed, cv1_algo, lpaq_path=lpaq_path)
            Path(out_path).write_bytes(decompressed)
            result.update(out_path=out_path, bytes=len(decompressed), compression=cv1_algo)
            return result
        except sv_compress.CompressError as e:
            return {'ok': False, 'error': f'Decompression failed: {e}'}
    finally:
        # Only delete the intermediate if it's a separate temp file.
        # When needs_decompress=False, intermediate == out_path and must be kept.
        if needs_decompress:
            Path(intermediate).unlink(missing_ok=True)


# ---------------------------------------------------------------------------

class DecodeApiMixin:
    """Decode-side methods: standard, brute-force, peek, and KV mode."""

    def decode(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            in_path = params['in_path']
        except KeyError as e:
            return {'ok': False, 'error': f'Missing param: {e}'}

        alph_id   = params.get('alph_id') or None
        password  = params.get('password') or None
        salt_mode = params.get('salt_mode', 'salt')

        out_path = _decode_resolve_out_path(in_path, params.get('out_path'))
        password = _decode_lookup_password(in_path, password)

        cv1_tmp = None
        try:
            decode_in, cv1_algo, cv1_tmp = _decode_strip_cv1(in_path)
            lpaq_path = _read_settings().get('lpaq_path', '')
            return _decode_and_decompress(
                decode_in, out_path, cv1_algo,
                alph_id, password, salt_mode, lpaq_path,
            )
        except Exception as e:
            # API contract: never raise to the JS layer.
            return {'ok': False, 'error': f'Decode failed: {e}'}
        finally:
            if cv1_tmp:
                try:
                    Path(cv1_tmp).unlink(missing_ok=True)
                except Exception:
                    pass

    def tryall(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            in_path = params['in_path']
        except KeyError as e:
            return {'ok': False, 'error': f'Missing param: {e}'}
        password = params.get('password') or None
        out_base = params.get('out_base') or str(Path(in_path).with_suffix('.tryall'))
        return sv_bridge.tryall(in_path, out_base, password)

    def peek_header(self, in_path: str) -> dict[str, Any]:
        """Read first bytes of file and parse CV1/SV1/KV headers without decoding."""
        try:
            text = Path(in_path).read_text(encoding='utf-8', errors='replace').strip()
        except Exception as e:
            return {'ok': False, 'error': f'Cannot read file: {e}'}

        # CV1 (compression) layer — outermost. Strip it but remember the algo.
        compression = sv_compress.ALGO_NONE
        cv1_algo, after_cv1 = sv_compress.parse_cv1_header(text)
        if cv1_algo != sv_compress.ALGO_NONE:
            compression = cv1_algo
            text = after_cv1

        # KV key-ref header: KV|XXXXXXXX|...
        mk = re.match(r'^KV\|([0-9a-f]{8})\|', text)
        if mk:
            record_id = mk.group(1)
            record = sv_keyrecord.get_record(record_id)
            alph_id = record.get('alphabet_id', '') if record else ''
            return {
                'ok': True, 'has_header': True, 'header_type': 'kv',
                'record_id': record_id,
                'alph_id': alph_id,
                'record_found': record is not None,
                'compression': compression,
                'preview': text[:80],
            }
        # SV1 with fingerprint
        m = re.match(r'^SV1\|fp:([0-9a-f]{2,8})\|b:(\d+)\|', text)
        if m:
            return {'ok': True, 'has_header': True, 'header_type': 'sv1',
                    'fp': m.group(1), 'base': int(m.group(2)),
                    'compression': compression, 'preview': text[:80]}
        # SV1 without fingerprint
        m2 = re.match(r'^SV1\|b:(\d+)\|', text)
        if m2:
            return {'ok': True, 'has_header': True, 'header_type': 'sv1',
                    'fp': '', 'base': int(m2.group(1)),
                    'compression': compression, 'preview': text[:80]}
        # No SV1/KV — but maybe just CV1 alone (bare compressed)
        if compression != sv_compress.ALGO_NONE:
            return {'ok': True, 'has_header': True, 'header_type': 'cv1',
                    'compression': compression, 'preview': text[:80]}
        return {'ok': True, 'has_header': False, 'header_type': 'none',
                'compression': 'none', 'preview': text[:80]}

    def decode_keyvault(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Decode a KV-encrypted encoded string.

        Params:
          encoded_string OR in_path — the tattoo string (or file containing it)
          record_id   — key record ID (optional; auto-detected from KV| prefix or by string search)
          password    — AES password (optional if stored in keyring)
          out_path    — where to write the recovered file

        Returns {ok, out_path, bytes, integrity_ok, preview, record}.
        """
        tmp_txt = tmp_bin = tmp_decrypted = None
        try:
            # 1. Encoded string
            encoded_string = _kv_get_encoded_string(params)

            # 2. Key record
            record = _kv_find_record(encoded_string, params.get('record_id') or '')

            # 3. Password
            password = _kv_get_password(params, record)

            # 4. Strip headers → raw base-encoded block + compression algo
            raw_encoded, cv1_algo = _kv_strip_headers(encoded_string, record)

            alph_id      = record.get('alphabet_id', '')
            salt_hex     = record.get('salt_hex', '')
            iv_hex       = record.get('iv_hex', '')
            settings     = _read_settings()
            openssl_path = settings.get('openssl_path', '')
            lpaq_path    = settings.get('lpaq_path', '')

            # 5. Output path
            out_path = params.get('out_path', '')
            if not out_path:
                base = label_to_filename(record.get('label') or record['id'])
                out_path = str(Path(tempfile.gettempdir()) / f'sv_decoded_{base}')

            # 6. Base-decode: encoded text → encrypted binary
            tmp_txt = tempfile.mktemp(prefix='sv_kvdec_enc_', suffix='.txt')
            tmp_bin = tempfile.mktemp(prefix='sv_kvdec_enc_', suffix='.bin')
            _kv_base_decode(raw_encoded, alph_id, tmp_txt, tmp_bin)

            # 7. KV decrypt: encrypted binary → plaintext (possibly compressed)
            tmp_decrypted = tempfile.mktemp(prefix='sv_kvdec_raw_', suffix='.bin')
            _kv_decrypt(tmp_bin, password, salt_hex, iv_hex, openssl_path, tmp_decrypted)

            # 8. Decompress (if needed) or move to final output
            _kv_decompress_or_move(tmp_decrypted, cv1_algo, out_path, lpaq_path)
            tmp_decrypted = None  # consumed by move/decompress

            # 9. Integrity check + text preview
            integrity_ok = sv_keyrecord.verify_integrity(record, out_path)
            preview = _kv_text_preview(out_path)
            out_size = Path(out_path).stat().st_size

            return {
                'ok':           True,
                'out_path':     out_path,
                'bytes':        out_size,
                'integrity_ok': integrity_ok,
                'preview':      preview,
                'record':       _safe_record(record),
            }

        except _KvError as e:
            return {'ok': False, 'error': str(e)}
        finally:
            for tmp in (tmp_txt, tmp_bin, tmp_decrypted):
                if tmp:
                    try:
                        Path(tmp).unlink(missing_ok=True)
                    except Exception:
                        pass
