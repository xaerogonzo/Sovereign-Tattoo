"""
sv_compress.py - Optional compression layer for Sovereign

Built-in algorithms (Python stdlib only, zero-byte stream headers):
  - zlib (raw deflate, wbits=-15)
  - lzma (FORMAT_RAW with LZMA2 preset 9 | EXTREME)

External algorithm (requires user-supplied binary):
  - lpaq — best for tiny English text. Path is auto-detected in common
    PEAzip install locations, or supplied via settings.

Pipeline position (encode):
    text/file → COMPRESS → encrypt → base-encode

Pipeline position (decode): reverse.

A compressed encoded string carries a 'CV1' prefix outside any SV1/KV
header so the decoder knows which algorithm to invert:
    CV1|c:l|SV1|fp:...|b:32|XXXXXXX...    (lzma + Full SV1)
    CV1|c:z|KV|a3f2b1c8|XXXXXXX...        (zlib + Key ref)
    CV1|c:p|XXXXXXX...                    (lpaq + bare)

If compression doesn't help (e.g. tiny input that inflates under
every algorithm), the encoder falls back to "none" and no CV1
prefix is added.
"""

from __future__ import annotations

import lzma
import re
import zlib
from pathlib import Path

import sv_engines

# ---------------------------------------------------------------------------
# Algorithm identifiers
# ---------------------------------------------------------------------------

ALGO_NONE = 'none'
ALGO_ZLIB = 'zlib'
ALGO_LZMA = 'lzma'

# Stdlib algorithms use single-char CV1 codes (kept short).
# External engines use the 'short' field from the sv_engines registry,
# which is currently always 2 chars (lp, po, zp).
CODE_FOR_ALGO = {
    ALGO_ZLIB: 'z',
    ALGO_LZMA: 'l',
}
# Pull in external-engine codes (e.g. {'lpaq8': 'lp', 'paq8o': 'po'})
for _eid, _entry in sv_engines.REGISTRY.items():
    if _entry.get('integrated'):
        CODE_FOR_ALGO[_eid] = _entry['short']
ALGO_FOR_CODE = {v: k for k, v in CODE_FOR_ALGO.items()}

# Convenience flag list for callers
EXTERNAL_ALGOS = [eid for eid, entry in sv_engines.REGISTRY.items() if entry.get('integrated')]

# LZMA filter chain — chosen for maximum compression on small text.
# We use raw LZMA2 at preset 9 (highest) + EXTREME mode so the output
# has zero metadata. We must use the same filters on decompress.
_LZMA_FILTERS = [
    {'id': lzma.FILTER_LZMA2, 'preset': 9 | lzma.PRESET_EXTREME},
]


class CompressError(Exception):
    """Raised when compression/decompression fails. Message is user-facing."""
    pass


# ---------------------------------------------------------------------------
# Core compression / decompression
# ---------------------------------------------------------------------------

def compress_bytes(data: bytes, algo: str, lpaq_path: str = '') -> bytes:
    """
    Compress *data* using *algo*. Raises CompressError on failure.

    *lpaq_path* is accepted for backward compatibility but ignored — external
    engines are now resolved via the sv_engines registry (bin/ folder).
    """
    if algo == ALGO_NONE:
        return data
    if algo == ALGO_ZLIB:
        co = zlib.compressobj(level=9, wbits=-15)
        return co.compress(data) + co.flush()
    if algo == ALGO_LZMA:
        return lzma.compress(data, format=lzma.FORMAT_RAW, filters=_LZMA_FILTERS)
    if algo in EXTERNAL_ALGOS:
        try:
            return sv_engines.compress(algo, data)
        except sv_engines.EngineError as e:
            raise CompressError(str(e))
    raise CompressError(f'Unknown compression algorithm: {algo!r}')


def decompress_bytes(data: bytes, algo: str, lpaq_path: str = '') -> bytes:
    """Decompress *data* produced by compress_bytes() with the same algo."""
    if algo == ALGO_NONE:
        return data
    if algo == ALGO_ZLIB:
        do = zlib.decompressobj(wbits=-15)
        return do.decompress(data) + do.flush()
    if algo == ALGO_LZMA:
        return lzma.decompress(data, format=lzma.FORMAT_RAW, filters=_LZMA_FILTERS)
    if algo in EXTERNAL_ALGOS:
        try:
            return sv_engines.decompress(algo, data)
        except sv_engines.EngineError as e:
            raise CompressError(str(e))
    raise CompressError(f'Unknown compression algorithm: {algo!r}')


def auto_compress(data: bytes, lpaq_path: str = '') -> tuple[str, bytes]:
    """
    Try each available algorithm (stdlib + every installed external engine)
    plus the uncompressed baseline. Return (algo, bytes) for the smallest.

    Falls back to ('none', data) if nothing beats the original.
    """
    candidates: list[tuple[str, bytes]] = [(ALGO_NONE, data)]
    # Always-available stdlib algos
    for algo in (ALGO_ZLIB, ALGO_LZMA):
        try:
            candidates.append((algo, compress_bytes(data, algo)))
        except Exception:
            pass
    # External engines that are installed in bin/
    for engine_id in EXTERNAL_ALGOS:
        if sv_engines.is_installed(engine_id):
            try:
                candidates.append((engine_id, compress_bytes(data, engine_id)))
            except Exception:
                pass
    best = min(candidates, key=lambda x: len(x[1]))
    return best


# ---------------------------------------------------------------------------
# CV1 header helpers
# ---------------------------------------------------------------------------

_CV1_RE = re.compile(r'^CV1\|c:([A-Za-z]{1,2})\|')


def build_cv1_header(algo: str) -> str:
    """Return the CV1 prefix for *algo*, or '' if no compression."""
    if algo == ALGO_NONE:
        return ''
    code = CODE_FOR_ALGO.get(algo)
    if not code:
        return ''
    return f'CV1|c:{code}|'


def parse_cv1_header(encoded: str) -> tuple[str, str]:
    """
    If *encoded* starts with a CV1 prefix, return (algo, rest_without_prefix).
    Otherwise return ('none', encoded) unchanged.
    """
    m = _CV1_RE.match(encoded)
    if not m:
        return (ALGO_NONE, encoded)
    return (ALGO_FOR_CODE.get(m.group(1), ALGO_NONE), encoded[m.end():])


# ---------------------------------------------------------------------------
# Self-test (run `python src/sv_compress.py`)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    sample = b'Hello, my name is John and this is a test of the Sovereign compression layer.'
    print(f'Original: {len(sample)} bytes')
    for algo in (ALGO_ZLIB, ALGO_LZMA):
        c = compress_bytes(sample, algo)
        d = decompress_bytes(c, algo)
        assert d == sample, f'{algo} round-trip failed'
        print(f'  {algo:6s}: {len(c)} bytes  ({len(c)/len(sample)*100:.1f}%)')
    for engine_id in EXTERNAL_ALGOS:
        if sv_engines.is_installed(engine_id):
            try:
                c = compress_bytes(sample, engine_id)
                d = decompress_bytes(c, engine_id)
                assert d == sample, f'{engine_id} round-trip failed'
                print(f'  {engine_id:6s}: {len(c)} bytes  ({len(c)/len(sample)*100:.1f}%)')
            except Exception as e:
                print(f'  {engine_id:6s}: ERROR {e}')
        else:
            print(f'  {engine_id:6s}: not installed')
    chosen, best = auto_compress(sample)
    print(f'Auto pick: {chosen} ({len(best)} bytes)')
