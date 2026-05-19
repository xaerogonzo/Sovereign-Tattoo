#Requires -Version 5.1
param(
    [Parameter(Mandatory)][string]$Mode,
    [string]$InFile     = '',
    [string]$OutFile    = '',
    [string]$AlphId     = '',
    [string]$Password   = '',
    [string]$Salt       = '',
    [string]$LibFile    = '',
    [switch]$SelfDesc,
    [switch]$DualVerify,
    [string]$KeyCardOut = '',
    [string]$FpSize    = '8'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---- Library ---------------------------------------------------------------
function Load-Library([string]$path) {
    if (-not (Test-Path $path)) { throw "Library not found: $path" }
    return (Get-Content $path -Raw | ConvertFrom-Json)
}

function Get-Alphabet($lib, [string]$id) {
    $e = $lib.alphabets | Where-Object { $_.id -eq $id }
    if (-not $e) { throw "Alphabet '$id' not found in library." }
    return $e
}

function Get-Fingerprint([string]$chars) {
    $sha  = [Security.Cryptography.SHA256]::Create()
    $hash = ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($chars)) |
             ForEach-Object { $_.ToString('x2') }) -join ''
    return $hash.Substring(0, 8)
}

# ---- Encoding engines ------------------------------------------------------
function Encode-Hex([byte[]]$raw) {
    return ([BitConverter]::ToString($raw) -replace '-', '')
}
function Decode-Hex([string]$txt) {
    $h = $txt.Trim()
    $b = New-Object byte[] ($h.Length / 2)
    for ($i = 0; $i -lt $h.Length; $i += 2) { $b[$i/2] = [Convert]::ToByte($h.Substring($i,2),16) }
    return $b
}

function Encode-B32([byte[]]$raw) {
    $a    = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    $bits = ($raw | ForEach-Object { [Convert]::ToString($_,2).PadLeft(8,'0') }) -join ''
    $o    = ''
    for ($i = 0; $i -lt $bits.Length; $i += 5) {
        $c = $bits.Substring($i, [Math]::Min(5,$bits.Length-$i)).PadRight(5,'0')
        $o += $a[[Convert]::ToInt32($c,2)]
    }
    return $o
}
function Decode-B32([string]$txt) {
    $a    = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    $bits = ($txt.Trim().ToUpper().ToCharArray() | ForEach-Object {
        $v = $a.IndexOf($_); if ($v -ge 0) { [Convert]::ToString($v,2).PadLeft(5,'0') }
    }) -join ''
    $bc = [Math]::Floor($bits.Length / 8)
    $b  = New-Object byte[] $bc
    for ($i = 0; $i -lt $bc; $i++) { $b[$i] = [Convert]::ToByte($bits.Substring($i*8,8),2) }
    return $b
}

function Encode-B64([byte[]]$raw) { return [Convert]::ToBase64String($raw) }
function Decode-B64([string]$txt) { return [Convert]::FromBase64String($txt.Trim()) }

function Encode-B85([byte[]]$raw, [string]$alph) {
    $pad = ((4 - ($raw.Length % 4)) % 4)
    $b2  = New-Object byte[] ($raw.Length + $pad)
    [Array]::Copy($raw, $b2, $raw.Length)
    $o = ''
    for ($i = 0; $i -lt $b2.Length; $i += 4) {
        $v = [uint32](($b2[$i]*16777216) + ($b2[$i+1]*65536) + ($b2[$i+2]*256) + $b2[$i+3])
        $chunk = ''
        for ($j = 0; $j -lt 5; $j++) { $chunk = $alph[[int]($v % 85)] + $chunk; $v = [Math]::Floor($v/85) }
        $o += $chunk
    }
    return $o.Substring(0, [Math]::Ceiling($raw.Length * 5 / 4))
}
function Decode-B85([string]$txt, [string]$alph) {
    $s       = $txt.Trim()
    $padChar = $alph[$alph.Length - 1]
    $pad     = ((5 - ($s.Length % 5)) % 5)
    $s2      = $s + [string]::new($padChar, $pad)
    $bytes   = New-Object System.Collections.Generic.List[byte]
    for ($i = 0; $i -lt $s2.Length; $i += 5) {
        $v = [uint32]0
        for ($j = 0; $j -lt 5; $j++) { $v = $v * 85 + [uint32]$alph.IndexOf($s2[$i+$j]) }
        $bytes.Add([byte](($v -shr 24) -band 0xFF))
        $bytes.Add([byte](($v -shr 16) -band 0xFF))
        $bytes.Add([byte](($v -shr  8) -band 0xFF))
        $bytes.Add([byte]( $v          -band 0xFF))
    }
    return $bytes.GetRange(0, $bytes.Count - $pad).ToArray()
}

function Encode-BigInt([byte[]]$raw, [string]$alph) {
    $base     = $alph.Length
    $sentinel = [byte[]]@(1) + $raw
    [array]::Reverse($sentinel)
    $n = [Numerics.BigInteger]::new($sentinel)
    $res = ''
    while ($n -gt 0) {
        $r = 0
        $n = [Numerics.BigInteger]::DivRem($n, $base, [ref]$r)
        $res = $alph[[int]$r] + $res
    }
    return $res
}
function Decode-BigInt([string]$txt, [string]$alph) {
    $base = $alph.Length
    $n    = [Numerics.BigInteger]::Zero
    foreach ($c in $txt.Trim().ToCharArray()) {
        $v = $alph.IndexOf($c); if ($v -ge 0) { $n = $n * $base + $v }
    }
    $b = $n.ToByteArray()
    if ($b.Length -gt 0 -and $b[-1] -eq 0) { $b = $b[0..($b.Length-2)] }
    [array]::Reverse($b)
    return $b[1..($b.Length-1)]
}

# ---- Dispatch --------------------------------------------------------------
function Encode-Data([byte[]]$raw, $entry) {
    switch ($entry.engine) {
        'hex'    { return Encode-Hex    $raw }
        'b32'    { return Encode-B32    $raw }
        'b64'    { return Encode-B64    $raw }
        'b85'    { return Encode-B85    $raw $entry.chars }
        'bigint' { return Encode-BigInt $raw $entry.chars }
        default  { throw "Unknown engine: $($entry.engine)" }
    }
}
function Decode-Data([string]$txt, $entry) {
    switch ($entry.engine) {
        'hex'    { return Decode-Hex    $txt }
        'b32'    { return Decode-B32    $txt }
        'b64'    { return Decode-B64    $txt }
        'b85'    { return Decode-B85    $txt $entry.chars }
        'bigint' { return Decode-BigInt $txt $entry.chars }
        default  { throw "Unknown engine: $($entry.engine)" }
    }
}

# ---- OpenSSL ---------------------------------------------------------------
function Invoke-SSL-Encrypt([string]$in, [string]$out, [string]$pass, [string]$saltMode) {
    $arg = if ($saltMode -eq 'nosalt') { '-nosalt' } else { '-salt' }
    $r   = & openssl aes-256-cbc $arg -pbkdf2 -iter 100000 -pass "pass:$pass" -in $in -out $out 2>&1
    if ($LASTEXITCODE -ne 0) { throw "OpenSSL encrypt failed: $r" }
}
function Invoke-SSL-Decrypt([string]$in, [string]$out, [string]$pass, [string]$saltMode) {
    $arg = if ($saltMode -eq 'nosalt') { '-nosalt' } else { '-salt' }
    $r   = & openssl aes-256-cbc -d $arg -pbkdf2 -iter 100000 -pass "pass:$pass" -in $in -out $out 2>&1
    if ($LASTEXITCODE -ne 0) { throw "OpenSSL decrypt failed (wrong password or salt mode?)" }
}

# ---- Key card --------------------------------------------------------------
function Write-KeyCard([string]$outPath, $entry) {
    $date        = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $testIn      = [byte[]](0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08)
    $testEncoded = Encode-Data $testIn $entry
    $testDecoded = Decode-Data $testEncoded $entry
    $testOk      = [System.Linq.Enumerable]::SequenceEqual([byte[]]$testIn,[byte[]]$testDecoded)
    $testStatus  = if ($testOk) { 'PASS' } else { 'FAIL -- DO NOT USE THIS ALPHABET' }
    $hexIn       = [BitConverter]::ToString($testIn) -replace '-',' '
    $hexOut      = [BitConverter]::ToString($testDecoded) -replace '-',' '
    $sep         = '=' * 80
    $sep2        = '-' * 80
    $lines = @(
        $sep,
        '                        SOVEREIGN KEY CARD',
        $sep,
        "Generated  : $date",
        "Alphabet   : $($entry.name)",
        "ID         : $($entry.id)",
        "Base       : $($entry.base)",
        "Fingerprint: $($entry.fingerprint)  (SHA256 of chars, first 8 hex digits)",
        "Engine     : $($entry.engine)",
        '',
        "Characters ($($entry.base)):",
        $entry.chars,
        '',
        "Notes: $($entry.notes)",
        $sep2,
        'VERIFICATION TEST VECTOR',
        "Input (hex) : $hexIn",
        "Encoded     : $testEncoded",
        "Decode back : $hexOut",
        "Result      : $testStatus",
        $sep2,
        'RECOVERY INSTRUCTIONS',
        '1. Find the header in the encoded string. Possible formats:',
        '   SV1|fp:XXXXXXXX|b:NN|...  (full 8-char fingerprint)',
        '   SV1|fp:XX|b:NN|...        (short 2-char fingerprint)',
        '   SV1|b:NN|...              (no fingerprint — match by base only)',
        '   (no header)               (use this key card to identify alphabet)',
        '2. Match the fingerprint to the one on this card.',
        '3. Paste the Characters string above into the Sovereign alphabet editor',
        '   or directly into sv_lib.json as a new entry with this fingerprint.',
        '4. Use Sovereign_Decode.bat with the recovered alphabet to decode.',
        '',
        'KEEP THIS CARD WITH MEDICAL RECORDS OR ESTATE DOCUMENTS.',
        'IF LOST, THE CHARACTERS STRING ABOVE IS THE ONLY RECOVERY MECHANISM.',
        $sep
    )
    [IO.File]::WriteAllText($outPath, ($lines -join "`r`n"), [Text.Encoding]::UTF8)
    return $testStatus
}

# ---- Roundtrip check -------------------------------------------------------
function Test-Roundtrip([byte[]]$original, [string]$encoded, $entry) {
    $dec = Decode-Data $encoded $entry
    return [System.Linq.Enumerable]::SequenceEqual([byte[]]$original, [byte[]]$dec)
}

# ===========================================================================
# MODE: ListLib
# ===========================================================================
if ($Mode -eq 'ListLib') {
    $lib = Load-Library $LibFile
    foreach ($a in $lib.alphabets) {
        Write-Output "$($a.id)`t$($a.name)`t$($a.base)`t$($a.fingerprint)`t$($a.engine)"
    }
    exit 0
}

# ===========================================================================
# MODE: KeyCard  (standalone, for any library entry)
# ===========================================================================
if ($Mode -eq 'KeyCard') {
    $lib    = Load-Library $LibFile
    $entry  = Get-Alphabet $lib $AlphId
    $status = Write-KeyCard $OutFile $entry
    Write-Output "KeyCard:$OutFile"
    Write-Output "TestVector:$status"
    exit 0
}

# ===========================================================================
# MODE: Encode
# ===========================================================================
if ($Mode -eq 'Encode') {
    if (-not $InFile  -or -not (Test-Path $InFile))  { throw "Input file not found: $InFile" }
    if (-not $OutFile) { throw "-OutFile required" }

    $lib      = Load-Library $LibFile
    $entry    = Get-Alphabet $lib $AlphId
    $rawBytes = [IO.File]::ReadAllBytes($InFile)

    # Encrypt if password given
    $workBytes = $rawBytes
    if ($Password) {
        $tmpEnc = [IO.Path]::GetTempFileName()
        try {
            Invoke-SSL-Encrypt $InFile $tmpEnc $Password $Salt
            $workBytes = [IO.File]::ReadAllBytes($tmpEnc)
        } finally { Remove-Item $tmpEnc -Force -ErrorAction SilentlyContinue }
    }

    # Encode
    $encoded = Encode-Data $workBytes $entry

    # Roundtrip verify
    if (-not (Test-Roundtrip $workBytes $encoded $entry)) {
        Write-Output 'ERROR:Roundtrip encode/decode mismatch. Aborted.'
        exit 1
    }

    # Dual-verify against hex
    if ($DualVerify) {
        $hexEnc = Encode-Hex $workBytes
        $hexDec = Decode-Hex $hexEnc
        if (-not [System.Linq.Enumerable]::SequenceEqual([byte[]]$workBytes,[byte[]]$hexDec)) {
            Write-Output 'ERROR:Dual-verify hex cross-check failed. Aborted.'
            exit 1
        }
        Write-Output 'DualVerified:OK'
    }

    # Self-describing header
    if ($SelfDesc) {
        switch ($FpSize) {
            '0' { $finalStr = "SV1|b:$($entry.base)|$encoded" }
            '2' { $finalStr = "SV1|fp:$($entry.fingerprint.Substring(0,2))|b:$($entry.base)|$encoded" }
            default { $finalStr = "SV1|fp:$($entry.fingerprint)|b:$($entry.base)|$encoded" }
        }
    } else {
        $finalStr = $encoded
    }

    # Write output
    [IO.File]::WriteAllText($OutFile, $finalStr, (New-Object Text.UTF8Encoding $false))

    # Key card (auto for custom/non-builtin, or explicit path given)
    if ($KeyCardOut -or (-not $entry.builtin)) {
        $kcPath = if ($KeyCardOut) { $KeyCardOut } else { "$OutFile.keycard.txt" }
        $kcStatus = Write-KeyCard $kcPath $entry
        Write-Output "KeyCard:$kcPath"
        Write-Output "KeyCardTest:$kcStatus"
    }

    Write-Output "OK:$OutFile"
    Write-Output "Chars:$($finalStr.Length)"
    Write-Output "AlphId:$($entry.id)"
    Write-Output "Fingerprint:$($entry.fingerprint)"
    Write-Output "FpSize:$FpSize"
    exit 0
}

# ===========================================================================
# MODE: Decode
# ===========================================================================
if ($Mode -eq 'Decode') {
    if (-not $InFile -or -not (Test-Path $InFile)) { throw "Input file not found: $InFile" }
    if (-not $OutFile) { throw "-OutFile required" }

    $lib = Load-Library $LibFile
    $raw = [IO.File]::ReadAllText($InFile, [Text.Encoding]::UTF8).Trim()

    # Auto-detect SV1 self-describing header (supports fp:XX, fp:XXXXXXXX, or no fingerprint)
    $detectedId = $AlphId
    if ($raw -match '^SV1\|fp:([0-9a-f]{2,8})\|b:(\d+)\|(.+)$') {
        $hdrFp  = $Matches[1]
        $raw    = $Matches[3]
        $found  = $lib.alphabets | Where-Object { $_.fingerprint.StartsWith($hdrFp) }
        if ($found) {
            if (@($found).Count -gt 1) {
                Write-Output "Warning:Short fingerprint $hdrFp matched multiple alphabets -- using first match"
                $found = @($found)[0]
            }
            $detectedId = $found.id
            Write-Output "AutoDetect:$($found.id) fp:$hdrFp"
        } else {
            Write-Output "Warning:Fingerprint $hdrFp not in library -- using specified alphabet"
        }
    } elseif ($raw -match '^SV1\|b:(\d+)\|(.+)$') {
        $hdrBase = $Matches[1]
        $raw     = $Matches[2]
        $found   = $lib.alphabets | Where-Object { [string]$_.base -eq $hdrBase }
        if ($found) {
            if (@($found).Count -gt 1) {
                Write-Output "Warning:Base $hdrBase matched multiple alphabets -- using specified or first"
                if ($AlphId) { $found = $lib.alphabets | Where-Object { $_.id -eq $AlphId } }
                else         { $found = @($found)[0] }
            }
            $detectedId = $found.id
            Write-Output "AutoDetect:$($found.id) b:$hdrBase (no fingerprint)"
        } else {
            Write-Output "Warning:Base $hdrBase not in library -- using specified alphabet"
        }
    }

    if (-not $detectedId) { throw "-AlphId required (no SV1 header and no -AlphId given)" }
    $entry        = Get-Alphabet $lib $detectedId
    $decodedBytes = Decode-Data $raw $entry

    # Decrypt if password given
    if ($Password) {
        $tmpIn  = [IO.Path]::GetTempFileName()
        $tmpDec = [IO.Path]::GetTempFileName()
        try {
            [IO.File]::WriteAllBytes($tmpIn, $decodedBytes)
            Invoke-SSL-Decrypt $tmpIn $tmpDec $Password $Salt
            $decodedBytes = [IO.File]::ReadAllBytes($tmpDec)
        } finally {
            Remove-Item $tmpIn  -Force -ErrorAction SilentlyContinue
            Remove-Item $tmpDec -Force -ErrorAction SilentlyContinue
        }
    }

    [IO.File]::WriteAllBytes($OutFile, $decodedBytes)
    Write-Output "OK:$OutFile"
    Write-Output "Bytes:$($decodedBytes.Length)"
    exit 0
}

# ===========================================================================
# MODE: TryAll  — brute-force try every built-in alphabet (no encryption)
# ===========================================================================
if ($Mode -eq 'TryAll') {
    if (-not $InFile -or -not (Test-Path $InFile)) { throw "Input file not found: $InFile" }
    if (-not $OutFile) { throw "-OutFile required (base name; alphabet id will be appended)" }

    $lib = Load-Library $LibFile
    $raw = [IO.File]::ReadAllText($InFile, [Text.Encoding]::UTF8).Trim()

    # Strip SV1 header if present (supports fp:XX, fp:XXXXXXXX, or no fingerprint)
    if ($raw -match '^SV1\|fp:([0-9a-f]{2,8})\|b:(\d+)\|(.+)$') {
        Write-Output "SV1Header:fp:$($Matches[1]) b:$($Matches[2])"
        $raw = $Matches[3]
    } elseif ($raw -match '^SV1\|b:(\d+)\|(.+)$') {
        Write-Output "SV1Header:b:$($Matches[1]) (no fingerprint)"
        $raw = $Matches[2]
    }

    # Build list of salt modes to try
    $saltModes = @('')
    if ($Password) {
        $saltModes = @('salt','nosalt')
    }

    $successCount = 0
    $tryCount     = 0
    foreach ($entry in $lib.alphabets) {
        foreach ($sm in $saltModes) {
            $tryCount++
            $label = if ($sm) { "$($entry.id)+$sm" } else { $entry.id }
            try {
                $decoded = Decode-Data $raw $entry
                if ($decoded.Length -eq 0) {
                    Write-Output "SKIP:$label|$($entry.name)|0 bytes"
                    continue
                }

                # If password given, try to decrypt
                if ($Password -and $sm) {
                    $tmpIn  = [IO.Path]::GetTempFileName()
                    $tmpDec = [IO.Path]::GetTempFileName()
                    try {
                        [IO.File]::WriteAllBytes($tmpIn, $decoded)
                        Invoke-SSL-Decrypt $tmpIn $tmpDec $Password $sm
                        $decoded = [IO.File]::ReadAllBytes($tmpDec)
                    } catch {
                        Write-Output "SKIP:$label|$($entry.name)|decrypt failed"
                        continue
                    } finally {
                        Remove-Item $tmpIn  -Force -ErrorAction SilentlyContinue
                        Remove-Item $tmpDec -Force -ErrorAction SilentlyContinue
                    }
                }

                $outPath = "$OutFile.$label"
                [IO.File]::WriteAllBytes($outPath, $decoded)
                $successCount++
                Write-Output "HIT:$label|$($entry.name)|$($decoded.Length) bytes|$outPath"
            } catch {
                Write-Output "SKIP:$label|$($entry.name)|$($_.Exception.Message)"
            }
        }
    }
    Write-Output "Tried:$tryCount"
    Write-Output "Hits:$successCount"
    exit 0
}

throw "Unknown Mode: $Mode  Valid: Encode, Decode, ListLib, KeyCard, TryAll"
