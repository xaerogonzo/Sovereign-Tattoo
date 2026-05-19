"""EncodeApiMixin — file encode, text encode, and Key Vault encode."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import sv_bridge
import sv_compress
import sv_keyring
import sv_keyrecord
import sv_kvcrypto

from ._helpers import (
    _KvError,
    _compress_to_tempfile,
    _kv_base_encode,
    _kv_build_tattoo_string,
    _kv_encrypt_to_temp,
    _kv_hash_source,
    _kv_lookup_alphabet,
    _kv_resolve_input,
    _read_settings,
    _safe_record,
)


class EncodeApiMixin:
    """Encode-side methods: standard, text, and KV mode."""

    def encode(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Params: in_path, alph_id, password (optional), salt_mode, selfdesc,
                fpsize, dualverify, save_password (bool, optional),
                compression ('none'|'auto'|'zlib'|'lzma'|'lpaq')
        """
        try:
            in_path = params['in_path']
            alph_id = params['alph_id']
        except KeyError as e:
            return {'ok': False, 'error': f'Missing param: {e}'}

        password   = params.get('password') or None
        salt_mode  = params.get('salt_mode', 'salt')
        selfdesc   = bool(params.get('selfdesc', False))
        fpsize     = str(params.get('fpsize', '8'))
        dualverify = bool(params.get('dualverify', False))
        save_pw    = bool(params.get('save_password', False))
        compression = params.get('compression', 'none') or 'none'

        out_path = params.get('out_path')
        if not out_path:
            ext = f'.sv{alph_id}' if password else f'.{alph_id}'
            out_path = in_path + ext

        # ----- Compression layer -----
        settings = _read_settings()
        lpaq_path = settings.get('lpaq_path', '')
        try:
            encode_in, applied_algo, cv1_prefix = _compress_to_tempfile(
                in_path, compression, lpaq_path
            )
        except sv_compress.CompressError as e:
            return {'ok': False, 'error': f'Compression failed: {e}'}

        compressed_tmp = encode_in if encode_in != in_path else None

        try:
            result = sv_bridge.encode(
                in_path=encode_in,
                out_path=out_path,
                alph_id=alph_id,
                password=password,
                salt_mode=salt_mode,
                selfdesc=selfdesc,
                fpsize=fpsize,
                dualverify=dualverify,
            )

            # Prepend CV1 header to the encoded output file
            if result.get('ok') and cv1_prefix:
                try:
                    p = Path(result.get('out_path', out_path))
                    existing = p.read_text(encoding='utf-8', errors='replace')
                    p.write_text(cv1_prefix + existing, encoding='utf-8')
                    result['chars'] = int(result.get('chars', 0)) + len(cv1_prefix)
                except Exception as e:
                    return {'ok': False, 'error': f'Failed to write CV1 header: {e}'}

            if result.get('ok'):
                result['compression'] = applied_algo

            if result.get('ok') and password and save_pw:
                label = sv_keyring.file_label(out_path)
                sv_keyring.save_password(label, password, hint=Path(out_path).name)
                result['password_label'] = label

            return result
        finally:
            if compressed_tmp:
                try:
                    Path(compressed_tmp).unlink(missing_ok=True)
                except Exception:
                    pass

    def encode_text(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Encode a plain-text string directly.
        Writes text to a temp file, encodes it, reads the result back,
        then cleans up the temp input. The encoded output file is kept.
        Params: same as encode() but with 'text' instead of 'in_path'.
        """
        text = params.get('text', '')
        if not text:
            return {'ok': False, 'error': 'No text provided'}

        # Write UTF-8 temp file
        try:
            tf = tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', suffix='.txt',
                prefix='sv_input_', delete=False,
            )
            tf.write(text)
            tf.close()
            tmp_path = tf.name
        except Exception as e:
            return {'ok': False, 'error': f'Failed to write temp file: {e}'}

        try:
            alph_id = params.get('alph_id', 'b32')
            password = params.get('password') or None
            compression = params.get('compression', 'none') or 'none'
            save_pw = bool(params.get('save_password', False))
            ext = f'.sv{alph_id}' if password else f'.{alph_id}'
            out_path = tmp_path + ext

            # Route through self.encode for the compression+encode pipeline.
            # save_password is handled here (not in self.encode) so the keyring
            # entry gets the 'text-input' hint instead of the temp-file name.
            sub_params = {
                'in_path':       tmp_path,
                'out_path':      out_path,
                'alph_id':       alph_id,
                'password':      password,
                'salt_mode':     params.get('salt_mode', 'salt'),
                'selfdesc':      bool(params.get('selfdesc', False)),
                'fpsize':        str(params.get('fpsize', '8')),
                'dualverify':    bool(params.get('dualverify', False)),
                'save_password': False,   # ← suppressed: see below
                'compression':   compression,
            }
            result = self.encode(sub_params)

            # Save password once, with the right hint.
            if result.get('ok') and password and save_pw:
                try:
                    label = sv_keyring.file_label(out_path)
                    sv_keyring.save_password(label, password, hint='text-input')
                    result['password_label'] = label
                except Exception:
                    pass

            # Embed the encoded string directly in the response
            if result.get('ok'):
                try:
                    result['encoded_text'] = Path(out_path).read_text(
                        encoding='utf-8', errors='replace'
                    ).strip()
                except Exception:
                    pass
                result['source'] = 'text'

            return result
        finally:
            # Clean up temp input file (encoded output is kept)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def encode_keyvault(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Encode in Key Vault mode: AES-256-CBC with salt/IV stored in the key
        record rather than in the encoded output.

        Params:
          in_path OR text — source (text takes priority if both present)
          alph_id         — alphabet to base-encode with
          password        — AES password (required)
          label           — human name for this record (optional)
          save_original   — bool: store original text in key record
          header_mode     — 'bare' | 'keyref' | 'fullsv1'
          fpsize          — '0'|'2'|'8' (for fullsv1 header)
          dualverify      — bool
          save_password   — bool: cache password in keyring
          save_record     — bool: persist to vault (default True)

        Returns {ok, id, encoded_string, char_count, fingerprint,
                 compression, dual_verified, record, record_saved}.
        """
        password = (params.get('password') or '').strip()
        if not password:
            return {'ok': False, 'error': 'Password is required for Key Vault encryption'}

        alph_id      = params.get('alph_id', 'b32')
        label        = params.get('label', '')
        save_original = bool(params.get('save_original', False))
        save_record  = bool(params.get('save_record', True))
        header_mode  = params.get('header_mode', 'keyref')
        fpsize       = str(params.get('fpsize', '8'))
        dualverify   = bool(params.get('dualverify', False))
        save_pw      = bool(params.get('save_password', False))
        compression  = params.get('compression', 'none') or 'none'
        settings     = _read_settings()
        openssl_path = settings.get('openssl_path', '')
        lpaq_path    = settings.get('lpaq_path', '')

        tmp_input = tmp_compressed = tmp_enc = tmp_encoded_out = None
        try:
            # 1. Resolve source → temp file (if text) or existing file
            in_path, tmp_input, original_text = _kv_resolve_input(
                params.get('text', ''), params.get('in_path', '')
            )
            original_text_to_store = original_text if save_original else ''

            # 2. Hash original BEFORE compression
            orig_sha256, orig_size = _kv_hash_source(in_path)

            # 3. Optional compression
            kv_input, applied_compression, cv1_prefix = _compress_to_tempfile(
                in_path, compression, lpaq_path
            )
            if kv_input != in_path:
                tmp_compressed = kv_input

            # 4. AES-256-CBC encrypt → temp binary
            rec_id = sv_keyrecord.generate_id()
            tmp_enc, salt_hex, iv_hex = _kv_encrypt_to_temp(kv_input, password, openssl_path)

            # 5. Base-encode the encrypted binary
            tmp_encoded_out, encode_result, encoded_raw = _kv_base_encode(
                tmp_enc, alph_id, header_mode == 'fullsv1', fpsize, dualverify
            )

            # 6. Assemble final tattoo string
            encoded_string = _kv_build_tattoo_string(encoded_raw, header_mode, rec_id, cv1_prefix)
            char_count = len(encoded_string)

            # 7. Alphabet metadata for key record
            alph_name, alph_base, alph_fp, alph_chars = _kv_lookup_alphabet(alph_id)
            alph_fp = alph_fp or encode_result.get('fingerprint', '')

            # 8. Build key record
            record: dict[str, Any] = {
                'id':                   rec_id,
                'label':                label or '',
                'header_mode':          header_mode,
                'alphabet_id':          alph_id,
                'alphabet_name':        alph_name,
                'alphabet_fingerprint': alph_fp,
                'alphabet_chars':       alph_chars,
                'base':                 alph_base,
                'encryption':           'aes256cbc-kv',
                'salt_hex':             salt_hex,
                'iv_hex':               iv_hex,
                **sv_kvcrypto.kdf_params(),
                'original_size_bytes':  orig_size,
                'original_sha256':      orig_sha256,
                'encoded_string':       encoded_string,
                'char_count':           char_count,
                'source':               'text' if params.get('text') else 'file',
                'openssl_cli':          sv_keyrecord.build_openssl_cli_hint(iv_hex),
                'compression':          applied_compression,
            }
            if original_text_to_store:
                record['original_text'] = original_text_to_store

            # 9. Persist (or skip) and optionally cache password
            if save_record:
                saved_record = sv_keyrecord.save_record(record)
                if save_pw:
                    try:
                        sv_keyring.save_password(rec_id, password, hint=label or f'kv-{rec_id}')
                    except Exception:
                        pass
            else:
                saved_record = record  # encode-only: nothing written to disk

            return {
                'ok':            True,
                'id':            rec_id,
                'encoded_string': encoded_string,
                'char_count':    char_count,
                'fingerprint':   alph_fp,
                'compression':   applied_compression,
                'dual_verified': encode_result.get('dual_verified', False),
                'record':        _safe_record(saved_record),
                'record_saved':  save_record,
            }

        except _KvError as e:
            return {'ok': False, 'error': str(e)}
        except sv_compress.CompressError as e:
            return {'ok': False, 'error': f'Compression failed: {e}'}
        finally:
            for tmp in (tmp_input, tmp_compressed, tmp_enc, tmp_encoded_out):
                if tmp:
                    try:
                        Path(tmp).unlink(missing_ok=True)
                    except Exception:
                        pass
