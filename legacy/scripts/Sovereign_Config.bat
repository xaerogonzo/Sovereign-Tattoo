@echo off
setlocal enabledelayedexpansion

:: Resolve project root: this script lives in legacy\scripts\, so walk up
:: two levels and let the for-loop normalize to an absolute path.
for %%A in ("%~dp0..\..") do set "root=%%~fA\"
set "cfg=!root!sovereign.cfg"
set "libfile=!root!sv_lib.json"
set "core=!root!sv_core.ps1"
set "default_alph=ABCDEFGHJKLMNPQRSTUVWXYZ23456789-_+=?~."
set "default_name=b39"

:: ---- Load existing config ----
set "peazip_exe="
set "custom_alph="
set "custom_name="
if exist "!cfg!" (
    for /f "usebackq tokens=1,* delims==" %%A in ("!cfg!") do (
        if "%%A"=="peazip"         set "peazip_exe=%%B"
        if "%%A"=="alphabet"       set "custom_alph=%%B"
        if "%%A"=="alphabet_name"  set "custom_name=%%B"
    )
)

:menu
cls
echo.
echo  ==========================================
echo         SOVEREIGN CONFIG
echo  ==========================================
echo.
echo  PeaZip : !peazip_exe!
echo  Library: !libfile!
if "!custom_alph!"=="" (
    echo  Legacy : [default !default_name!] !default_alph!
) else (
    echo  Legacy : [!custom_name!] !custom_alph!
)
echo.
echo  ==========================================
echo   [1] Set legacy alphabet by typing
echo   [2] Set legacy alphabet from file  (drag .txt onto this script^)
echo   [3] Set PeaZip path
echo   [4] Reset legacy alphabet to default ^(!default_name!^)
echo   [5] Show legacy alphabet stats
echo   [6] Manage alphabet library ^(sv_lib.json^)
echo   [7] Exit
echo  ==========================================
echo.
set "choice="
set /p "choice=Select: "

if "!choice!"=="1" goto :type_alph
if "!choice!"=="2" goto :file_alph
if "!choice!"=="3" goto :set_peazip
if "!choice!"=="4" goto :reset_alph
if "!choice!"=="5" goto :show_stats
if "!choice!"=="6" goto :manage_lib
if "!choice!"=="7" exit /b
goto :menu

:: ================================================================
:type_alph
echo.
echo  Enter your alphabet string (all characters on one line, no spaces^):
echo  Current: !custom_alph!
echo.
set "new_alph="
set /p "new_alph=Alphabet: "
if "!new_alph!"=="" goto :menu
call :validate_alph "!new_alph!"
if "!alph_ok!"=="0" goto :menu
set "custom_alph=!new_alph!"
call :compute_base "!custom_alph!"
set "custom_name=b!computed_base!"
call :save_cfg
echo.
echo  [OK] Alphabet saved as !custom_name! ^(!computed_base! chars^)
pause & goto :menu

:file_alph
if "%~1"=="" (
    echo.
    echo  [INFO] Re-run this script with a .txt file dragged onto it.
    echo  The file should contain just the alphabet string on one line.
    pause & goto :menu
)
set "alphfile=%~1"
set "new_alph="
for /f "usebackq tokens=*" %%A in ("!alphfile!") do (
    if "!new_alph!"=="" set "new_alph=%%A"
)
if "!new_alph!"=="" (
    echo [ERROR] File was empty or unreadable.
    pause & goto :menu
)
call :validate_alph "!new_alph!"
if "!alph_ok!"=="0" goto :menu
set "custom_alph=!new_alph!"
call :compute_base "!custom_alph!"
set "custom_name=b!computed_base!"
call :save_cfg
echo.
echo  [OK] Alphabet saved as !custom_name! ^(!computed_base! chars^)
pause & goto :menu

:set_peazip
echo.
set /p "newpath=Enter full path to peazip.exe: "
set "peazip_exe=!newpath!"
call :save_cfg
echo [OK] Saved.
pause & goto :menu

:reset_alph
set "custom_alph="
set "custom_name="
call :save_cfg
echo.
echo  [OK] Alphabet reset to default ^(!default_name!^).
pause & goto :menu

:show_stats
echo.
if "!custom_alph!"=="" (
    set "show=!default_alph!"
    set "sname=!default_name! (default)"
) else (
    set "show=!custom_alph!"
    set "sname=!custom_name!"
)
call :compute_base "!show!"
echo  Alphabet : !sname!
echo  String   : !show!
echo  Base     : !computed_base!
echo.
powershell -NoProfile -Command ^
    "$b=!computed_base!;" ^
    "$lg=[Math]::Log($b,2);" ^
    "Write-Host ('  bits/char : '+$lg.ToString('F2'));" ^
    "Write-Host ('  Nosalt 64B: '+[Math]::Ceiling(64*8/$lg)+' chars');" ^
    "Write-Host ('  Salted 80B: '+[Math]::Ceiling(80*8/$lg)+' chars');"
echo.
pause & goto :menu

:: ================================================================
:manage_lib
cls
echo.
echo  ==========================================
echo   ALPHABET LIBRARY  ^(!libfile!^)
echo  ==========================================
echo.
if not exist "!libfile!" (
    echo  [!] sv_lib.json not found. Run Sovereign_Encode.bat first.
    echo.
    pause & goto :menu
)
set "lcount=0"
for /f "tokens=1-4 delims=	" %%A in ('powershell -NoProfile -ExecutionPolicy Bypass -File "!core!" -Mode ListLib -LibFile "!libfile!"') do (
    set /a lcount+=1
    set "lid!lcount!=%%A"
    set "lname!lcount!=%%B"
    set "lbase!lcount!=%%C"
    set "lfp!lcount!=%%D"
)
for /l %%i in (1,1,!lcount!) do (
    set "_bi="
    powershell -NoProfile -Command ^
        "$j=Get-Content '!libfile!' -Raw|ConvertFrom-Json;" ^
        "$e=$j.alphabets|?{$_.id -eq '!lid%%i!'};" ^
        "if($e.builtin){'builtin'}else{'custom'}" > "!temp!\sv_ltype.tmp" 2>nul
    set /p "_bi=" < "!temp!\sv_ltype.tmp"
    del "!temp!\sv_ltype.tmp" 2>nul
    echo   [%%i]  !lname%%i!  b!lbase%%i!  fp:!lfp%%i!  ^(!_bi!^)
)
echo.
echo  To add:    drag a .svlib file onto sv_import.bat
echo  To delete: type the number of the entry to remove
echo.
echo   [B] Back
echo  ==========================================
echo.
set "lc=" & set /p "lc=Choice: "
if /i "!lc!"=="b" goto :menu

set "del_idx=0"
for /l %%i in (1,1,!lcount!) do (
    if "!lc!"=="%%i" set "del_idx=%%i"
)
if "!del_idx!"=="0" ( echo [ERROR] Invalid choice. & pause & goto :manage_lib )

set "_delid=!lid%del_idx%!"
set "_delname=!lname%del_idx%!"

:: Check if builtin — prevent deletion
powershell -NoProfile -Command ^
    "$j=Get-Content '!libfile!' -Raw|ConvertFrom-Json;" ^
    "$e=$j.alphabets|?{$_.id -eq '!_delid!'};" ^
    "if($e.builtin){'builtin'}else{'custom'}" > "!temp!\sv_ltype.tmp" 2>nul
set "_dtype="
set /p "_dtype=" < "!temp!\sv_ltype.tmp"
del "!temp!\sv_ltype.tmp" 2>nul

if "!_dtype!"=="builtin" (
    echo.
    echo  [ERROR] Cannot delete built-in alphabet '!_delname!'.
    pause & goto :manage_lib
)

echo.
echo  Delete '!_delname!' ^(id: !_delid!^)?
set "conf=" & set /p "conf=Type YES to confirm: "
if not "!conf!"=="YES" ( echo [Cancelled] & pause & goto :manage_lib )

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$j=Get-Content '!libfile!' -Raw|ConvertFrom-Json;" ^
    "$j.alphabets=[object[]]($j.alphabets|?{$_.id -ne '!_delid!'});" ^
    "$j|ConvertTo-Json -Depth 5|Set-Content '!libfile!' -Encoding UTF8;" ^
    "Write-Host '[OK] Deleted: !_delname!'"
echo.
pause & goto :manage_lib

:: ================================================================
:validate_alph
set "alph_ok=1"
set "test=%~1"
:: Check length >= 2
set "len=0"
for /l %%i in (0,1,200) do (
    set "ch=!test:~%%i,1!"
    if not "!ch!"=="" set /a len+=1
)
if !len! lss 2 (
    echo [ERROR] Alphabet must have at least 2 characters.
    set "alph_ok=0"
    pause
    exit /b
)
:: Check for duplicate chars via PowerShell
for /f %%A in ('powershell -NoProfile -Command ^
    "$s='!test!';$u=$s.ToCharArray()|Sort-Object|Get-Unique;if($u.Count -eq $s.Length){'OK'}else{'DUP'}"') do set "dup_check=%%A"
if "!dup_check!"=="DUP" (
    echo [ERROR] Alphabet contains duplicate characters.
    set "alph_ok=0"
    pause
)
exit /b

:compute_base
set "computed_base=0"
for /f %%A in ('powershell -NoProfile -Command "'%~1'.Length"') do set "computed_base=%%A"
exit /b

:save_cfg
(
    if not "!peazip_exe!"==""  echo peazip=!peazip_exe!
    if not "!custom_alph!"=="" echo alphabet=!custom_alph!
    if not "!custom_name!"=="" echo alphabet_name=!custom_name!
) > "!cfg!"
exit /b
