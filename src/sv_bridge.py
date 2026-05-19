"""
sv_bridge.py - Subprocess wrapper around sv_core.ps1

Calls the existing PowerShell engine and parses its key:value line output
into Python dicts. The GUI never reimplements encoding/decoding logic.

All methods return a dict with at minimum {'ok': bool}. On failure,
{'ok': False, 'error': '...'} is returned (no exceptions propagate to JS).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


class SovereignError(Exception):
    """Internal exception; converted to {'ok': False, 'error': ...} at API boundary."""
    pass


# ---------------------------------------------------------------------------
# Path resolution -- find the project root (where sv_core.ps1 lives).
# This file may live in a src/ subdirectory, so we check both here and parent.
# ---------------------------------------------------------------------------

def project_root() -> Path:
    """Return the directory containing sv_core.ps1."""
    here = Path(__file__).resolve().parent
    for candidate in (here, here.parent):
        if (candidate / 'sv_core.ps1').exists():
            return candidate
    raise SovereignError(
        f'sv_core.ps1 not found (searched {here} and {here.parent})'
    )


def core_path() -> Path:
    return project_root() / 'sv_core.ps1'


def lib_path() -> Path:
    return project_root() / 'data' / 'sv_lib.json'


# ---------------------------------------------------------------------------
# Low-level subprocess invocation
# ---------------------------------------------------------------------------

def _run_powershell(args: list[str], timeout: int = 120) -> tuple[int, str]:
    """
    Invoke PowerShell with sv_core.ps1 and the given args. Returns (exit_code, combined_output).
    Captures stdout+stderr together so error messages are visible.
    """
    cmd = [
        'powershell.exe',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', str(core_path()),
        *args,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            creationflags=0x08000000 if os.name == 'nt' else 0,  # CREATE_NO_WINDOW
        )
    except subprocess.TimeoutExpired:
        raise SovereignError(f'PowerShell timed out after {timeout}s')
    except FileNotFoundError:
        raise SovereignError('powershell.exe not found on PATH')

    output = (proc.stdout or '') + (proc.stderr or '')
    return proc.returncode, output


def _parse_kv(output: str) -> dict[str, Any]:
    """
    Parse sv_core.ps1's key:value line output into a dict.
    Multiple HIT: lines accumulate into a list under the 'hits' key.
    """
    result: dict[str, Any] = {'_raw': output, 'hits': [], 'warnings': []}
    for line in output.splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        key, _, val = line.partition(':')
        key = key.strip()
        val = val.strip()
        if key == 'HIT':
            result['hits'].append(val)
        elif key == 'SKIP':
            pass  # ignore skips
        elif key == 'Warning':
            result['warnings'].append(val)
        elif key == 'ERROR':
            result['error'] = val
        else:
            # Store lowercase key, last value wins
            result[key.lower()] = val
    return result


# ---------------------------------------------------------------------------
# High-level mode wrappers
# ---------------------------------------------------------------------------

def list_alphabets() -> list[dict[str, Any]]:
    """Returns list of alphabet entries. Tab-separated output from sv_core.ps1 ListLib."""
    code, output = _run_powershell(['-Mode', 'ListLib', '-LibFile', str(lib_path())])
    if code != 0:
        raise SovereignError(f'ListLib failed: {output}')
    alphabets: list[dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) < 5:
            continue
        alphabets.append({
            'id': parts[0],
            'name': parts[1],
            'base': int(parts[2]),
            'fingerprint': parts[3],
            'engine': parts[4],
            'builtin': False,  # filled in below
        })

    # Read sv_lib.json to enrich with builtin flag and notes.
    try:
        lib = json.loads(lib_path().read_text(encoding='utf-8'))
        builtin_map = {a['id']: bool(a.get('builtin', False)) for a in lib.get('alphabets', [])}
        notes_map = {a['id']: a.get('notes', '') for a in lib.get('alphabets', [])}
        for a in alphabets:
            a['builtin'] = builtin_map.get(a['id'], False)
            a['notes'] = notes_map.get(a['id'], '')
    except Exception:
        pass
    return alphabets


def encode(
    in_path: str,
    out_path: str,
    alph_id: str,
    password: str | None = None,
    salt_mode: str = 'salt',
    selfdesc: bool = False,
    fpsize: str = '8',
    dualverify: bool = False,
) -> dict[str, Any]:
    """Encode a file. Returns parsed result dict (ok, out_path, chars, etc.)."""
    args = [
        '-Mode', 'Encode',
        '-InFile', in_path,
        '-OutFile', out_path,
        '-AlphId', alph_id,
        '-LibFile', str(lib_path()),
    ]
    if password:
        args += ['-Password', password, '-Salt', salt_mode]
    if selfdesc:
        args += ['-SelfDesc', '-FpSize', fpsize]
    if dualverify:
        args += ['-DualVerify']

    code, output = _run_powershell(args)
    parsed = _parse_kv(output)
    if code != 0 or 'ok' not in parsed:
        return {'ok': False, 'error': parsed.get('error') or output.strip() or 'Encode failed'}
    return {
        'ok': True,
        'out_path': parsed.get('ok', out_path),
        'chars': int(parsed.get('chars', 0)),
        'alph_id': parsed.get('alphid', alph_id),
        'fingerprint': parsed.get('fingerprint', ''),
        'keycard_path': parsed.get('keycard'),
        'keycard_test': parsed.get('keycardtest'),
        'fp_size': parsed.get('fpsize', fpsize),
        'dual_verified': 'dualverified' in parsed,
    }


def decode(
    in_path: str,
    out_path: str,
    alph_id: str | None = None,
    password: str | None = None,
    salt_mode: str = 'salt',
) -> dict[str, Any]:
    """Decode a file. AlphId optional if SV1 header present."""
    args = [
        '-Mode', 'Decode',
        '-InFile', in_path,
        '-OutFile', out_path,
        '-LibFile', str(lib_path()),
    ]
    if alph_id:
        args += ['-AlphId', alph_id]
    if password:
        args += ['-Password', password, '-Salt', salt_mode]

    code, output = _run_powershell(args)
    parsed = _parse_kv(output)
    if code != 0 or 'ok' not in parsed:
        return {'ok': False, 'error': parsed.get('error') or output.strip() or 'Decode failed'}
    return {
        'ok': True,
        'out_path': parsed.get('ok', out_path),
        'bytes': int(parsed.get('bytes', 0)),
        'autodetect': parsed.get('autodetect'),
        'warnings': parsed.get('warnings', []),
    }


def tryall(in_path: str, out_base: str, password: str | None = None) -> dict[str, Any]:
    """Brute-force try every alphabet. Returns list of hits."""
    args = [
        '-Mode', 'TryAll',
        '-InFile', in_path,
        '-OutFile', out_base,
        '-LibFile', str(lib_path()),
    ]
    if password:
        args += ['-Password', password]

    code, output = _run_powershell(args, timeout=300)
    parsed = _parse_kv(output)
    if code != 0:
        return {'ok': False, 'error': parsed.get('error') or output.strip() or 'TryAll failed'}
    hits: list[dict[str, Any]] = []
    for h in parsed.get('hits', []):
        parts = h.split('|')
        if len(parts) >= 4:
            hits.append({
                'label': parts[0],
                'name': parts[1],
                'bytes_desc': parts[2],
                'path': parts[3],
            })
    return {
        'ok': True,
        'tried': int(parsed.get('tried', 0)),
        'hit_count': int(parsed.get('hits_count', len(hits))) if 'hits_count' in parsed else len(hits),
        'hits': hits,
        'sv1_header': parsed.get('sv1header'),
    }


def key_card(alph_id: str, out_path: str) -> dict[str, Any]:
    """Generate a standalone key card for the given alphabet."""
    args = [
        '-Mode', 'KeyCard',
        '-AlphId', alph_id,
        '-OutFile', out_path,
        '-LibFile', str(lib_path()),
    ]
    code, output = _run_powershell(args)
    parsed = _parse_kv(output)
    if code != 0:
        return {'ok': False, 'error': parsed.get('error') or output.strip() or 'KeyCard failed'}
    return {
        'ok': True,
        'keycard_path': parsed.get('keycard', out_path),
        'test_vector': parsed.get('testvector', 'UNKNOWN'),
    }


# ---------------------------------------------------------------------------
# Library file operations (no PowerShell needed -- pure Python)
# ---------------------------------------------------------------------------

def read_library() -> dict[str, Any]:
    return json.loads(lib_path().read_text(encoding='utf-8'))


def write_library(lib: dict[str, Any]) -> None:
    """Atomic write via .tmp + os.replace (see sv_keyrecord._write_store)."""
    p = lib_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(lib, indent=2), encoding='utf-8')
    os.replace(tmp, p)


def import_svlib(svlib_path: str) -> dict[str, Any]:
    """Import an .svlib file into sv_lib.json. Mirrors sv_import.bat logic."""
    try:
        import_data = json.loads(Path(svlib_path).read_text(encoding='utf-8'))
    except Exception as e:
        return {'ok': False, 'error': f'Failed to read .svlib: {e}'}

    entry = import_data.get('entry')
    if not entry:
        return {'ok': False, 'error': 'Invalid .svlib file (no entry field)'}

    lib = read_library()
    if any(a['id'] == entry['id'] for a in lib.get('alphabets', [])):
        return {'ok': False, 'error': f"Alphabet ID '{entry['id']}' already exists in library"}

    lib.setdefault('alphabets', []).append(entry)
    write_library(lib)
    return {'ok': True, 'alphabet': entry}


def save_alphabet(entry: dict[str, Any]) -> dict[str, Any]:
    """Direct save from embedded editor -- no file dance."""
    required = {'id', 'name', 'chars', 'base', 'engine', 'fingerprint'}
    missing = required - set(entry.keys())
    if missing:
        return {'ok': False, 'error': f'Missing fields: {", ".join(sorted(missing))}'}

    # Ensure optional fields have defaults so sv_core.ps1 doesn't throw on missing properties
    entry.setdefault('notes', '')
    entry.setdefault('builtin', False)

    lib = read_library()
    # Replace existing entry with same id, otherwise append.
    alphabets = lib.get('alphabets', [])
    existing = next((a for a in alphabets if a['id'] == entry['id']), None)
    if existing:
        if existing.get('builtin'):
            return {'ok': False, 'error': f"Cannot overwrite builtin alphabet '{entry['id']}'"}
        alphabets[:] = [entry if a['id'] == entry['id'] else a for a in alphabets]
    else:
        alphabets.append(entry)
    lib['alphabets'] = alphabets
    write_library(lib)
    return {'ok': True, 'alphabet': entry}


def delete_alphabet(alph_id: str) -> dict[str, Any]:
    lib = read_library()
    alphabets = lib.get('alphabets', [])
    target = next((a for a in alphabets if a['id'] == alph_id), None)
    if not target:
        return {'ok': False, 'error': f"Alphabet '{alph_id}' not found"}
    if target.get('builtin'):
        return {'ok': False, 'error': f"Cannot delete builtin alphabet '{alph_id}'"}
    lib['alphabets'] = [a for a in alphabets if a['id'] != alph_id]
    write_library(lib)
    return {'ok': True}


# ---------------------------------------------------------------------------
# Self-test (run `python src/sv_bridge.py` from project root to verify)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print('Project root:', project_root())
    print('Core script :', core_path())
    print('Library     :', lib_path())
    print()
    print('Alphabets:')
    for a in list_alphabets():
        flag = '[builtin]' if a['builtin'] else '[custom]'
        print(f"  {flag} {a['id']:8s} b{a['base']:<3} fp:{a['fingerprint']}  {a['name']}")
