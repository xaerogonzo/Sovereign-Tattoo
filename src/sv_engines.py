"""
sv_engines.py - External compression engine registry & management

Sovereign keeps a list of supported external compression binaries. Users
install them by dropping the .exe into  <project_root>/bin/  or by clicking
"Browse for binary..." in the Settings tab — Sovereign copies it into bin/
so future launches detect it automatically.

We do not download binaries automatically (initial design). The registry
records the homepage URL for each engine so users can fetch them manually
from the original sources.

Each registry entry knows how to invoke the engine via subprocess with
{exe}, {input}, {output} placeholders.

Currently supported:
  - lpaq8  : Matt Mahoney's lightweight PAQ.  Strongest on tiny text.
  - paq8o  : Heavier PAQ variant.  Better compression on slightly larger inputs.
  - zpaq   : Listed for documentation; CLI is archive-format only and not yet
             wrapped here.  Future work.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class EngineError(Exception):
    """Raised when an external engine call fails. User-facing message."""
    pass


# ---------------------------------------------------------------------------
# Project / bin paths
# ---------------------------------------------------------------------------

# Single authoritative root resolver lives in sv_bridge — import it here so
# every storage module agrees on what "project root" means.
from sv_bridge import project_root as _project_root  # noqa: E402


def bin_dir() -> Path:
    """The folder Sovereign looks in for external engine binaries."""
    d = _project_root() / 'bin'
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Each entry:
#   filename         — the binary's expected name inside bin/
#   compress_argv    — argv template for compression (list of strings; {} placeholders)
#   decompress_argv  — same for decompression
#   in_place_suffix  — if set, engine writes output as <input>+suffix (no explicit out arg)
#   homepage         — URL where user can download the binary
#   sha256           — empty placeholder; user can verify externally
#   integrated       — True if compress/decompress is wired up; False = registry-only

REGISTRY: dict[str, dict[str, Any]] = {
    'lpaq8': {
        'id':              'lpaq8',
        'name':            'LPAQ8',
        'short':           'lp',           # CV1 single/double-char code
        'family':          'paq',
        'description':     ("Matt Mahoney's lightweight PAQ context-mixing compressor. "
                            "Best fit for very short text (under ~200 chars). "
                            "Public domain, ~50 KB binary."),
        'filename':        'lpaq8.exe',
        'compress_argv':   ['{exe}', '9', '{input}', '{output}'],
        'decompress_argv': ['{exe}', 'd', '{input}', '{output}'],
        'in_place_suffix': '',
        'homepage':        'http://mattmahoney.net/dc/lpaq.html',
        'license':         'Public domain',
        'integrated':      True,
    },
    'paq8o': {
        'id':              'paq8o',
        'name':            'PAQ8O',
        'short':           'po',
        'family':          'paq',
        'description':     ("Heavier PAQ variant by Matt Mahoney. Typically 10-20% smaller "
                            "output than LPAQ8 on text 100+ chars, but slower. "
                            "Uses level -4 (~135 MB model) for broad compatibility. "
                            "GPL, ~250 KB binary."),
        'filename':        'paq8o.exe',
        # PAQ8 series writes output as <input>.paq8o — no output arg accepted.
        # Level -4 (~135 MB RAM). Higher levels (e.g. -8) may fail with
        # "Out of memory" on machines with limited physical RAM.
        'compress_argv':   ['{exe}', '-4', '{input}'],
        'decompress_argv': ['{exe}', '-d', '{input}'],
        'in_place_suffix': '.paq8o',
        'homepage':        'http://mattmahoney.net/dc/',
        'license':         'GPL',
        'integrated':      True,
    },
    'zpaq': {
        'id':              'zpaq',
        'name':            'ZPAQ',
        'short':           'zp',
        'family':          'paq',
        'description':     ("Newer PAQ-family archival compressor. Listed here for reference — "
                            "ZPAQ's CLI is archive-format only and not yet wired into Sovereign. "
                            "Useful info: weak on very short inputs, strong on KB+ files."),
        'filename':        'zpaq.exe',
        'compress_argv':   [],   # not wired
        'decompress_argv': [],
        'in_place_suffix': '',
        'homepage':        'http://mattmahoney.net/dc/zpaq.html',
        'license':         'Public domain',
        'integrated':      False,
    },
}


# ---------------------------------------------------------------------------
# Discovery / install state
# ---------------------------------------------------------------------------

def engine_path(engine_id: str) -> str:
    """
    Full path to the engine binary, else ''.

    Search order:
    1. Exact top-level: bin/<filename>         (canonical install location)
    2. Recursive search: bin/**/<filename>     (user-placed in a versioned subfolder)

    When multiple matches exist in subdirectories the most recently modified
    file wins, so a "v5/" folder beats "v4/" automatically.
    """
    entry = REGISTRY.get(engine_id)
    if not entry:
        return ''

    # 1. Canonical top-level location (fastest path, no recursion needed)
    canonical = bin_dir() / entry['filename']
    if canonical.is_file():
        return str(canonical)

    # 2. Recursive search — user dropped the binary inside a version subfolder
    matches = [p for p in bin_dir().rglob(entry['filename']) if p.is_file()]
    if not matches:
        return ''
    # Prefer most recently modified (higher version folders typically have newer mtimes)
    best = max(matches, key=lambda p: p.stat().st_mtime)
    return str(best)


def is_installed(engine_id: str) -> bool:
    return bool(engine_path(engine_id))


def list_engines() -> list[dict[str, Any]]:
    """Return registry entries with installation status filled in."""
    out = []
    for eid, entry in REGISTRY.items():
        e = dict(entry)
        path = engine_path(eid)
        canonical = str(bin_dir() / entry['filename'])
        e['installed'] = bool(path)
        e['installed_path'] = path
        # True when found at the canonical top-level bin/<filename> location.
        # False when discovered in a version subfolder via recursive search.
        e['is_canonical'] = (path == canonical) if path else False
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# Install / remove
# ---------------------------------------------------------------------------

def install_from_path(engine_id: str, source_path: str) -> str:
    """
    Copy a user-supplied binary into bin/ under the registry's expected
    filename.  Returns the new path.  Raises EngineError on failure.
    """
    entry = REGISTRY.get(engine_id)
    if not entry:
        raise EngineError(f'Unknown engine: {engine_id!r}')

    src = Path(source_path)
    if not src.is_file():
        raise EngineError(f'Source file does not exist: {source_path!r}')

    dest = bin_dir() / entry['filename']
    try:
        shutil.copy2(src, dest)
    except Exception as e:
        raise EngineError(f'Failed to copy binary: {e}')
    return str(dest)


def remove_engine(engine_id: str) -> bool:
    """
    Delete the engine's binary from bin/.  Returns True if something was removed.

    Only removes the canonical top-level copy (bin/<filename>).  If the binary
    was discovered via recursive subfolder search we do NOT delete it — those
    files live in user-managed version folders that Sovereign doesn't own.
    """
    entry = REGISTRY.get(engine_id)
    if not entry:
        return False
    p = bin_dir() / entry['filename']
    if p.is_file():
        try:
            p.unlink()
            return True
        except Exception:
            return False
    return False


# ---------------------------------------------------------------------------
# Compress / decompress dispatch
# ---------------------------------------------------------------------------

def _run(argv: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=180,
            creationflags=0x08000000 if os.name == 'nt' else 0,
        )
    except FileNotFoundError as e:
        raise EngineError(f'Engine binary not found: {e}')
    except subprocess.TimeoutExpired:
        raise EngineError('Engine timed out (>3 minutes).')
    output = (proc.stdout or b'') + (proc.stderr or b'')
    return proc.returncode, output.decode('utf-8', errors='replace').strip()


def _resolve_engine(engine_id: str, op_label: str) -> tuple[dict, str]:
    """
    Look up an engine entry and its installed executable path.

    Returns (entry, exe). Raises EngineError if the engine isn't integrated
    for the requested operation, or if its binary isn't installed in bin/.
    *op_label* is 'compress' or 'decompress' — included in error messages
    so failures from a batch of round-trips identify which side broke.
    """
    entry = REGISTRY.get(engine_id)
    if not entry or not entry.get('integrated'):
        raise EngineError(
            f'Engine {engine_id!r} not integrated for {op_label}'
        )
    exe = engine_path(engine_id)
    if not exe:
        raise EngineError(
            f'{entry["name"]} is not installed (needed for {op_label}). '
            f'Drop {entry["filename"]} into {bin_dir()} or use the Settings tab.'
        )
    return entry, exe


def _run_in_place_engine(
    entry: dict,
    exe: str,
    data: bytes,
    argv_key: str,
    in_name: str,
    out_name: str,
    op_label: str,
) -> bytes:
    """
    Drive an in-place engine (PAQ8O-style): write *data* to a fresh tmpdir
    as *in_name*, invoke the engine with cwd=tmpdir, read back *out_name*.

    The engine binary must accept relative filenames — PAQ8O stores the
    bare input name in its archive header, so symmetric compress/decompress
    requires consistent basenames across both calls.

    *argv_key* picks 'compress_argv' or 'decompress_argv' from the registry.
    *op_label* is woven into every EngineError so callers can tell which
    operation failed without inspecting a stack trace.
    """
    with tempfile.TemporaryDirectory(prefix='sv_paq_') as tmp_str:
        tmp_dir = Path(tmp_str)
        in_path = tmp_dir / in_name
        out_path = tmp_dir / out_name
        in_path.write_bytes(data)

        argv_tpl = entry[argv_key]
        argv = [t.format(exe=exe, input=in_name, output='') for t in argv_tpl if t]
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=180,
            cwd=str(tmp_dir),
            creationflags=0x08000000 if os.name == 'nt' else 0,
        )
        if proc.returncode != 0:
            msg = ((proc.stdout or b'') + (proc.stderr or b'')).decode(
                'utf-8', errors='replace'
            ).strip()
            raise EngineError(
                f'{entry["name"]} {op_label} failed (exit {proc.returncode}): '
                f'{msg or "no output"}'
            )
        if not out_path.is_file():
            raise EngineError(
                f'{entry["name"]} {op_label} produced no output file '
                f'(expected {out_path.name})'
            )
        result = out_path.read_bytes()
        if not result:
            raise EngineError(
                f'{entry["name"]} {op_label} produced empty output — '
                f'{"input may be too small" if op_label == "compress" else "archive may be corrupt"}'
            )
        return result


def _run_explicit_engine(
    entry: dict,
    exe: str,
    data: bytes,
    argv_key: str,
    op_label: str,
) -> bytes:
    """
    Drive an explicit-output engine (LPAQ8-style): write *data* to a named
    temp file, invoke the engine with -i/-o style args, read the output file.

    Reuses the shared `_run(argv)` helper for subprocess + timeout handling.
    """
    in_tmp = tempfile.NamedTemporaryFile(prefix='sv_eng_', suffix='.in', delete=False)
    in_tmp.write(data)
    in_tmp.close()
    out_path = in_tmp.name + '.out'
    argv = [t.format(exe=exe, input=in_tmp.name, output=out_path)
            for t in entry[argv_key]]
    try:
        code, msg = _run(argv)
        if code != 0:
            raise EngineError(
                f'{entry["name"]} {op_label} failed (exit {code}): {msg or "no output"}'
            )
        if not Path(out_path).is_file():
            raise EngineError(
                f'{entry["name"]} {op_label} produced no output file'
            )
        return Path(out_path).read_bytes()
    finally:
        for p in (in_tmp.name, out_path):
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass


def compress(engine_id: str, data: bytes) -> bytes:
    """Compress *data* using engine *engine_id*. Raises EngineError on failure."""
    entry, exe = _resolve_engine(engine_id, 'compress')
    suffix = entry.get('in_place_suffix', '')
    if suffix:
        return _run_in_place_engine(
            entry, exe, data, 'compress_argv',
            in_name='sv_data', out_name='sv_data' + suffix,
            op_label='compress',
        )
    return _run_explicit_engine(entry, exe, data, 'compress_argv', 'compress')


def decompress(engine_id: str, data: bytes) -> bytes:
    """Decompress *data* using engine *engine_id*. Raises EngineError on failure."""
    entry, exe = _resolve_engine(engine_id, 'decompress')
    suffix = entry.get('in_place_suffix', '')
    if suffix:
        return _run_in_place_engine(
            entry, exe, data, 'decompress_argv',
            in_name='sv_data' + suffix, out_name='sv_data',
            op_label='decompress',
        )
    return _run_explicit_engine(entry, exe, data, 'decompress_argv', 'decompress')


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print(f'bin/ directory: {bin_dir()}')
    print()
    for e in list_engines():
        flag = '[installed]' if e['installed'] else '[not installed]'
        print(f'  {flag} {e["id"]:8s} ({e["name"]}) — {e["filename"]}')
        if e['installed']:
            print(f'      path: {e["installed_path"]}')
    print()
    print('Drop binaries into the bin/ folder to enable them.')
