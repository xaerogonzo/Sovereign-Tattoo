"""
install_tesseract.py — Install Tesseract OCR portably into bin/tesseract/.

Usage (from anywhere — the script finds project root automatically):
    python scripts/install_tesseract.py             # install (skip if present)
    python scripts/install_tesseract.py --force     # reinstall
    python scripts/install_tesseract.py --remove    # delete bin/tesseract/

Or double-click `scripts/install_tesseract.bat`.

What it does:
    1. Downloads the UB-Mannheim Windows installer (~50 MB) over HTTPS.
    2. Silent-installs it to a temp scratch directory (per-user, no admin
       prompt; /CURRENTUSER bypasses UAC).
    3. Copies the entire install tree to bin/tesseract/.
    4. Silent-uninstalls from the scratch directory to clean up registry
       entries and Start Menu shortcuts. Our copy under bin/tesseract/
       remains untouched and unregistered — truly portable.
    5. Replaces the installer's tessdata language files with the
       higher-accuracy tessdata_best variants (eng + osd, ~32 MB total).
    6. Verifies by running `bin/tesseract/tesseract.exe --version`.

After running this once, Sovereign auto-detects bin/tesseract/ ahead of any
system install (see _TesseractAdapter._resolve_cmd in src/sv_tattoo.py).
Nuitka builds pick it up automatically via the build_nuitka.py --include-data-dir.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


def _find_project_root() -> Path:
    """Walk up from this script's location until sv_core.ps1 is found."""
    here = Path(__file__).resolve().parent
    for candidate in (here, here.parent, here.parent.parent):
        if (candidate / 'sv_core.ps1').is_file():
            return candidate
    raise SystemExit(
        f'Project root not found (searched upward from {here}). '
        f'Expected sv_core.ps1 at the root.'
    )


ROOT = _find_project_root()
TARGET = ROOT / 'bin' / 'tesseract'

# Pinned installer release. Update INSTALLER_VERSION + INSTALLER_URL when bumping.
INSTALLER_VERSION = '5.5.0.20241111'
INSTALLER_URL = (
    f'https://github.com/UB-Mannheim/tesseract/releases/download/'
    f'v{INSTALLER_VERSION}/tesseract-ocr-w64-setup-{INSTALLER_VERSION}.exe'
)

# tessdata_best — highest-accuracy LSTM models. Apache 2.0 / community-licensed.
# Hosted on Google's official tesseract-ocr mirror.
TESSDATA_BASE = 'https://github.com/tesseract-ocr/tessdata_best/raw/main'
LANG_FILES = ('eng.traineddata', 'osd.traineddata')


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _human_bytes(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} B'
        n /= 1024
    return f'{n:.1f} TB'


def _download(url: str, dest: Path, label: str) -> None:
    print(f'  Downloading {label}')
    print(f'    {url}')
    last_pct = [-1]

    def hook(blocks: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        pct = int(blocks * block_size * 100 / total_size)
        if pct != last_pct[0] and pct % 5 == 0:
            sys.stdout.write(f'\r    {pct:3d}%  ({_human_bytes(blocks * block_size)} / {_human_bytes(total_size)})')
            sys.stdout.flush()
            last_pct[0] = pct

    urllib.request.urlretrieve(url, dest, reporthook=hook)
    print(f'\r    100%  ({_human_bytes(dest.stat().st_size)})            ')


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, capturing both streams; raise SystemExit on non-zero."""
    print(f'  $ {" ".join(cmd)}')
    r = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if r.returncode != 0:
        if r.stdout:
            print(r.stdout)
        if r.stderr:
            print(r.stderr, file=sys.stderr)
        raise SystemExit(f'Command failed with exit code {r.returncode}: {cmd[0]}')
    return r


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def _silent_install(installer: Path, scratch: Path) -> None:
    """
    Run the Inno Setup installer in fully silent + per-user mode.
    /CURRENTUSER avoids the UAC prompt — install lands under the user profile
    and doesn't touch HKLM.
    """
    print(f'  Silent-installing to {scratch}')
    args = [
        str(installer),
        '/VERYSILENT',          # no UI at all
        '/SUPPRESSMSGBOXES',    # no warning popups
        '/CURRENTUSER',         # per-user, no admin prompt
        '/NORESTART',
        '/NOCANCEL',
        f'/DIR={scratch}',
        '/COMPONENTS=tesseract',  # skip ScrollView / training tools — saves ~80 MB
        '/TASKS=',                # no shortcuts, no PATH entry
    ]
    # subprocess.run waits for the installer to finish
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        if r.stdout:
            print(r.stdout)
        if r.stderr:
            print(r.stderr, file=sys.stderr)
        raise SystemExit(
            f'Tesseract installer exited with code {r.returncode}. '
            f'If /CURRENTUSER fails on your machine, try running this script '
            f'from an Administrator shell.'
        )


def _silent_uninstall(install_dir: Path) -> None:
    """
    Run the Inno-generated unins000.exe in silent mode against the *scratch*
    install directory. This cleans up:
      - The scratch directory (which we've already copied out of)
      - Start Menu shortcuts placed by the installer
      - Registry entries under HKCU\\Software\\Microsoft\\Windows\\...\\Uninstall\\
    Our bin/tesseract/ copy is unaffected because the uninstaller only knows
    about the scratch path it was registered against.
    """
    uninst = install_dir / 'unins000.exe'
    if not uninst.is_file():
        print('  (No unins000.exe found — registry entries may remain.)')
        return
    print('  Silent-uninstalling scratch install (cleans registry + shortcuts)')
    subprocess.run(
        [str(uninst), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
        check=False,
    )


def _copy_install(src: Path, dst: Path) -> None:
    """
    Copy the entire installed tree to *dst*. Replaces an existing *dst* in
    place. Uses copytree for atomicity.
    """
    print(f'  Copying install tree → {dst}')
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _replace_tessdata(target: Path) -> None:
    """
    Swap the installer-shipped tessdata for the higher-accuracy tessdata_best
    eng + osd files. Keeps everything else (configs, etc.) untouched.
    """
    tessdata = target / 'tessdata'
    if not tessdata.is_dir():
        # Some installer configurations skip this — create it
        tessdata.mkdir(parents=True)

    # Wipe any existing .traineddata so the new versions are unambiguous
    for existing in tessdata.glob('*.traineddata'):
        existing.unlink()
        print(f'  Removed {existing.name}')

    print('  Downloading tessdata_best (~32 MB total)')
    for name in LANG_FILES:
        _download(f'{TESSDATA_BASE}/{name}', tessdata / name, f'tessdata_best/{name}')


def _verify(target: Path) -> None:
    exe = target / 'tesseract.exe'
    if not exe.is_file():
        raise SystemExit(f'Verification failed: {exe} not found.')
    print(f'  Verifying: {exe} --version')
    env = os.environ.copy()
    env['TESSDATA_PREFIX'] = str(target / 'tessdata')
    r = subprocess.run([str(exe), '--version'], capture_output=True, text=True, env=env)
    out = (r.stdout or '') + (r.stderr or '')
    print('  ' + out.strip().splitlines()[0] if out.strip() else '  (no version output)')

    # Smoke test: list available languages
    r2 = subprocess.run([str(exe), '--list-langs'], capture_output=True, text=True, env=env)
    out2 = (r2.stdout or '') + (r2.stderr or '')
    langs = [ln.strip() for ln in out2.splitlines() if ln.strip() and not ln.startswith('List of')]
    print(f'  Languages installed: {", ".join(langs)}')
    if 'eng' not in langs:
        raise SystemExit('Verification failed: eng language data not detected.')


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def install(force: bool = False) -> None:
    if TARGET.exists() and not force:
        print(f'{TARGET} already exists. Use --force to reinstall.')
        return

    if os.name != 'nt':
        raise SystemExit('install_tesseract.py only supports Windows. '
                         'On Linux/macOS, install Tesseract via your package manager '
                         'and set the path in Settings.')

    print('=== Sovereign Tattoo — portable Tesseract installer ===')
    print(f'Target: {TARGET}')
    print()

    with tempfile.TemporaryDirectory(prefix='sv_tess_') as td:
        td_path = Path(td)
        installer = td_path / 'tesseract_installer.exe'
        scratch = td_path / 'install'

        print('Step 1/5 — download installer')
        _download(INSTALLER_URL, installer, 'UB-Mannheim Tesseract installer')

        print('\nStep 2/5 — silent install to scratch dir')
        _silent_install(installer, scratch)

        print('\nStep 3/5 — copy to bin/tesseract/')
        _copy_install(scratch, TARGET)

        print('\nStep 4/5 — uninstall scratch (cleans registry/shortcuts)')
        _silent_uninstall(scratch)

    print('\nStep 5/5 — replace tessdata with tessdata_best + verify')
    _replace_tessdata(TARGET)
    _verify(TARGET)

    print()
    print('=== Done. ===')
    print(f'Tesseract is now installed portably at {TARGET}.')
    print('The Sovereign app will auto-detect it ahead of any system install.')
    print('Nuitka builds will bundle bin/tesseract/ automatically.')


def remove() -> None:
    if not TARGET.exists():
        print(f'{TARGET} does not exist; nothing to remove.')
        return
    print(f'Removing {TARGET}...')
    shutil.rmtree(TARGET)
    print('Done.')


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--force', action='store_true', help='Reinstall even if bin/tesseract/ exists')
    p.add_argument('--remove', action='store_true', help='Delete bin/tesseract/ and exit')
    args = p.parse_args()

    if args.remove:
        remove()
    else:
        install(force=args.force)


if __name__ == '__main__':
    main()
