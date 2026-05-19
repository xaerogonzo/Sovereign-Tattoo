# bin/ — External compression engines

This folder holds optional compression binaries that Sovereign can use.
The folder is auto-created on first launch; engines are installed by the
user (we don't redistribute them).

Sovereign detects engines by **exact filename** — drop a binary in here
with the expected name and the corresponding option lights up on the
Encode tab.

## Supported engines

| Filename     | Engine | Source                                 | License        |
|--------------|--------|----------------------------------------|----------------|
| `lpaq8.exe`  | LPAQ8  | http://mattmahoney.net/dc/lpaq.html    | Public domain  |
| `paq8o.exe`  | PAQ8O  | http://mattmahoney.net/dc/             | GPL            |
| `zpaq.exe`   | ZPAQ   | http://mattmahoney.net/dc/zpaq.html    | Public domain  |

> **ZPAQ** is listed in the registry but not yet wired up for compression
> (its CLI is archive-format only). Future work.

## How to install

1. Open the Settings tab → **Compression engines** section
2. Click the homepage link for the engine you want
3. Download the `.zip` from the source
4. Extract the `.exe` (e.g. `lpaq8.exe` from `lpaq8.zip`)
5. Use **Browse for binary…** in Settings, *or* drop the `.exe` directly
   into this folder

Sovereign auto-detects engines on every launch. Click **Refresh** in
Settings to re-scan without restarting.

## Why isn't this auto-download?

Three reasons:

1. **Antivirus** — most AV vendors quarantine arbitrarily-downloaded `.exe`
   files. A "Sovereign downloaded an unsigned binary" event is a much
   worse user experience than "open this URL and save the file."
2. **Transport security** — Matt Mahoney's site is plain HTTP. Auto-downloading
   over HTTP without a known SHA-256 to verify against is sketchy.
3. **Provenance** — the user can verify the file's hash against multiple
   public references before trusting it on their machine.

If you'd like to skip the manual step, run a one-line PowerShell:
```powershell
iwr http://mattmahoney.net/dc/lpaq8.zip -OutFile lpaq8.zip
Expand-Archive lpaq8.zip
Move-Item lpaq8/lpaq8.exe ./
```

## Built-in fallback

Sovereign always supports **zlib** (raw deflate) and **lzma** (raw LZMA2)
via Python stdlib — no external binaries needed. These cover the
common case. The external engines are for power users squeezing the
last few bytes out of tiny English text.
