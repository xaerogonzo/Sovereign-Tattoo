@echo off
setlocal enabledelayedexpansion

if "%~1"=="" (
    echo [ERROR] Drag an encoded file onto this script.
    pause & exit /b
)

set "src=%~1"
set "src_name=%~n1"
set "src_ext=%~x1"
:: Resolve project root: this script lives in legacy\scripts\, so walk up
:: two levels and let the for-loop normalize to an absolute path.
for %%A in ("%~dp0..\..") do set "dir=%%~fA\"
set "libfile=!dir!sv_lib.json"
set "core=!dir!sv_core.ps1"

if not exist "!core!"    ( echo [ERROR] sv_core.ps1 not found. & pause & exit /b )
if not exist "!libfile!" ( echo [ERROR] sv_lib.json not found. & pause & exit /b )

for /f %%A in ('powershell -NoProfile -Command "(Get-Item -LiteralPath '!src!').Length"') do set "srcbytes=%%A"

:: ---- Peek for SV1 self-describing header ------------------------------------
set "sv1_fp="
set "sv1_b="
for /f "tokens=*" %%A in ('powershell -NoProfile -Command ^
    "$t=[IO.File]::ReadAllText('!src!').Trim();" ^
    "if($t -match '^SV1\|fp:([0-9a-f]{2,8})\|b:(\d+)\|'){Write-Host ($Matches[1]+'|'+$Matches[2])}" ^
    "elseif($t -match '^SV1\|b:(\d+)\|'){Write-Host ('|'+$Matches[1])}" ^
    "else{Write-Host ''}"') do (
    set "_sv1=%%A"
)
if defined _sv1 if not "!_sv1!"=="" (
    for /f "tokens=1,2 delims=|" %%A in ("!_sv1!") do (
        set "sv1_fp=%%A"
        set "sv1_b=%%B"
    )
)

:: ---- Build alphabet list from library --------------------------------------
set "alphcount=0"
for /f "tokens=1-5 delims=	" %%A in ('powershell -NoProfile -ExecutionPolicy Bypass -File "!core!" -Mode ListLib -LibFile "!libfile!"') do (
    set /a alphcount+=1
    set "aid!alphcount!=%%A"
    set "aname!alphcount!=%%B"
    set "abase!alphcount!=%%C"
    set "afp!alphcount!=%%D"
    set "aeng!alphcount!=%%E"
)

:: ---- Try to auto-match alphabet from SV1 fingerprint -----------------------
set "auto_idx=0"
if not "!sv1_fp!"=="" (
    for /l %%i in (1,1,!alphcount!) do (
        set "_cfp=!afp%%i!"
        if "!_cfp!"=="!sv1_fp!" set "auto_idx=%%i"
        if "!_cfp:~0,2!"=="!sv1_fp!" if "!auto_idx!"=="0" set "auto_idx=%%i"
    )
) else if not "!sv1_b!"=="" (
    for /l %%i in (1,1,!alphcount!) do (
        if "!abase%%i!"=="!sv1_b!" if "!auto_idx!"=="0" set "auto_idx=%%i"
    )
)

:menu_alph
cls
echo.
echo  ============================================================
echo          SOVEREIGN DECODE
echo  ============================================================
echo   File : !src_name!!src_ext!  ^(!srcbytes! bytes^)
if not "!sv1_fp!"=="" (
    echo   SV1  : fp:!sv1_fp!  b!sv1_b!  ^(self-describing header detected^)
) else if not "!sv1_b!"=="" (
    echo   SV1  : b!sv1_b!  ^(header detected, no fingerprint^)
)
echo  ============================================================
echo.
if not "!auto_idx!"=="0" (
    echo   [A]  Auto-detected: !aname%auto_idx%!  b!abase%auto_idx%!  fp:!sv1_fp!
    echo.
)
echo   SELECT DECODING ALPHABET:
echo.
for /l %%i in (1,1,!alphcount!) do (
    set "_nm=!aname%%i!"
    set "_b=!abase%%i!"
    set "_fp=!afp%%i!"
    set "_eng=!aeng%%i!"
    set "_tag="
    if not "!_eng!"=="hex" if not "!_eng!"=="b32" if not "!_eng!"=="b64" if not "!_eng!"=="b85" (
        set "_tag= ^(fp:!_fp!^)"
    )
    echo   [%%i]  !_nm!!_tag!
)
echo.
echo   [T]  Try ALL built-in alphabets ^(brute-force^)
echo   [Q]  Quit
echo  ============================================================
echo.
set "choice="
set /p "choice=Select alphabet: "

if /i "!choice!"=="q" exit /b
if /i "!choice!"=="t" goto :try_all
if /i "!choice!"=="a" (
    if "!auto_idx!"=="0" ( echo [ERROR] No auto-detected alphabet. & pause & goto :menu_alph )
    set "alph_idx=!auto_idx!"
    goto :menu_enc
)

set "alph_idx=0"
for /l %%i in (1,1,!alphcount!) do (
    if "!choice!"=="%%i" set "alph_idx=%%i"
)
if "!alph_idx!"=="0" ( echo [ERROR] Invalid choice. & pause & goto :menu_alph )

:menu_enc
set "sel_id=!aid%alph_idx%!"
set "sel_name=!aname%alph_idx%!"
set "sel_base=!abase%alph_idx%!"
set "sel_fp=!afp%alph_idx%!"

cls
echo.
echo  ============================================================
echo          SOVEREIGN DECODE
echo  ============================================================
echo   File    : !src_name!!src_ext!  ^(!srcbytes! bytes^)
echo   Alphabet: !sel_name!  b!sel_base!  fp:!sel_fp!
echo  ============================================================
echo.
echo   ENCRYPTION:
echo   [1]  None  ^(file was not encrypted^)
echo   [2]  Salted AES-256
echo   [3]  No-salt AES-256
echo.
echo   [B]  Back to alphabet selection
echo  ============================================================
echo.
set "choice2="
set /p "choice2=Select: "

if /i "!choice2!"=="b" goto :menu_alph
if "!choice2!"=="1" ( set "enc_mode=none"   & goto :do_decode )
if "!choice2!"=="2" ( set "enc_mode=salt"   & goto :ask_pass )
if "!choice2!"=="3" ( set "enc_mode=nosalt" & goto :ask_pass )
echo [ERROR] Invalid choice. & pause & goto :menu_enc

:ask_pass
set "vbs=!temp!\sv_pass.vbs"
echo pass = InputBox("Enter decryption password:", "Sovereign") : WScript.StdOut.Write pass > "!vbs!"
set "pass="
for /f "tokens=*" %%A in ('cscript //nologo "!vbs!"') do set "pass=%%A"
del "!vbs!" 2>nul
if "!pass!"=="" ( echo [CANCELLED] & pause & goto :menu_enc )
goto :do_decode

:do_decode
:: Output filename: src_name already has the encoded extension stripped by %~n1
:: (e.g. dragging "photo.jpg.svb37" gives src_name="photo.jpg.svb37" minus the .svb37 extension)
:: Actually %~n1 strips only the LAST extension. So "photo.jpg.svb37" → src_name="photo.jpg" src_ext=".svb37"
:: That means outfile = src_name is already correct.
set "outfile=!src_name!"

echo.
echo  Decoding...

set "ps_args=-Mode Decode"
set "ps_args=!ps_args! -InFile "!src!""
set "ps_args=!ps_args! -OutFile "!outfile!""
set "ps_args=!ps_args! -AlphId !sel_id!"
set "ps_args=!ps_args! -LibFile "!libfile!""
if not "!enc_mode!"=="none" (
    set "ps_args=!ps_args! -Password "!pass!" -Salt !enc_mode!"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "!core!" !ps_args! > "!temp!\sv_result.tmp" 2>&1

set "ok=0" & set "outbytes=?" & set "autodet="
for /f "tokens=1,* delims=:" %%A in ('type "!temp!\sv_result.tmp"') do (
    if "%%A"=="OK"         set "ok=1"
    if "%%A"=="Bytes"      set "outbytes=%%B"
    if "%%A"=="AutoDetect" set "autodet=%%B"
    if "%%A"=="Warning"    echo  [WARNING] %%B
    if "%%A"=="ERROR"      echo  [ERROR] %%B
)
del "!temp!\sv_result.tmp" 2>nul

if "!ok!"=="0" ( echo  [FAILED] & pause & goto :menu_alph )

echo.
echo  ============================================================
if not "!autodet!"=="" echo   [AUTO-DETECT] Used alphabet:!autodet!
echo   [OK] File  : !outfile!
echo   [OK] Bytes : !outbytes!
echo  ============================================================
pause & goto :menu_alph

:try_all
cls
echo.
echo  ============================================================
echo   BRUTE-FORCE DECODE — trying all !alphcount! library alphabets
echo  ============================================================
echo   File: !src_name!!src_ext!  ^(!srcbytes! bytes^)
echo.
echo   This will attempt to decode with every alphabet in the library
echo   and write each successful result as a separate file.
echo   You can then inspect the outputs to find the correct one.
echo.
echo   Was this file encrypted?
echo   [1]  No  — raw encode, no password
echo   [2]  Yes — I know the password
echo.
echo   [B]  Back
echo  ============================================================
echo.
set "ta_choice=" & set /p "ta_choice=Select: "
if /i "!ta_choice!"=="b" goto :menu_alph

set "ta_pass="
if "!ta_choice!"=="2" (
    set "vbs=!temp!\sv_pass.vbs"
    echo pass = InputBox("Enter decryption password:", "Sovereign") : WScript.StdOut.Write pass > "!vbs!"
    for /f "tokens=*" %%A in ('cscript //nologo "!vbs!"') do set "ta_pass=%%A"
    del "!vbs!" 2>nul
    if "!ta_pass!"=="" ( echo [CANCELLED] & pause & goto :menu_alph )
    echo.
    echo  Will try each alphabet x salted + nosalt ^(!alphcount! x 2 = attempts^)
) else if "!ta_choice!"=="1" (
    echo.
    echo  Will try each alphabet raw ^(!alphcount! attempts^)
) else (
    echo [ERROR] Invalid choice. & pause & goto :try_all
)

echo.
echo  Working...

set "outbase=!src_name!.tryall"
set "ps_args=-Mode TryAll"
set "ps_args=!ps_args! -InFile "!src!""
set "ps_args=!ps_args! -OutFile "!outbase!""
set "ps_args=!ps_args! -LibFile "!libfile!""
if not "!ta_pass!"=="" (
    set "ps_args=!ps_args! -Password "!ta_pass!""
)

powershell -NoProfile -ExecutionPolicy Bypass -File "!core!" !ps_args! > "!temp!\sv_result.tmp" 2>&1

echo.
echo  ============================================================
echo   RESULTS
echo  ============================================================
set "hitcount=0" & set "trycount=0"
for /f "tokens=1,* delims=:" %%A in ('type "!temp!\sv_result.tmp"') do (
    if "%%A"=="SV1Header" echo   [SV1] %%B
    if "%%A"=="HIT"       ( set /a hitcount+=1 & echo   [OK]   %%B )
    if "%%A"=="SKIP"      echo   [SKIP] %%B
    if "%%A"=="Tried"     set "trycount=%%B"
    if "%%A"=="Hits"      set "hitcount=%%B"
)
del "!temp!\sv_result.tmp" 2>nul
echo  ============================================================
echo   Tried: !trycount! alphabets    Decoded: !hitcount! candidates
echo.
echo   Inspect the output files to find the correct one.
echo   Correct file = original byte count + opens in expected app.
echo  ============================================================
pause & goto :menu_alph
