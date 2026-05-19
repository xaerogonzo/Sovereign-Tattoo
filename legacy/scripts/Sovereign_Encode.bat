@echo off
setlocal enabledelayedexpansion

if "%~1"=="" (
    echo [ERROR] Drag a file onto this script.
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

:: ---- Build alphabet list from library -------------------------------------
set "alphcount=0"
for /f "tokens=1-5 delims=	" %%A in ('powershell -NoProfile -ExecutionPolicy Bypass -File "!core!" -Mode ListLib -LibFile "!libfile!"') do (
    set /a alphcount+=1
    set "aid!alphcount!=%%A"
    set "aname!alphcount!=%%B"
    set "abase!alphcount!=%%C"
    set "afp!alphcount!=%%D"
    set "aeng!alphcount!=%%E"
)

set "sv_selfdesc=0"
set "sv_dualverify=0"
set "sv_fpsize=8"

:menu_alph
cls
echo.
echo  ============================================================
echo          SOVEREIGN ENCODE
echo  ============================================================
echo   File : !src_name!!src_ext!  ^(!srcbytes! bytes^)
echo  ============================================================
echo.
echo   SELECT ENCODING ALPHABET:
echo.
for /l %%i in (1,1,!alphcount!) do (
    set "_b=!abase%%i!"
    set "_sz=!srcbytes!"
    set "_fp=!afp%%i!"
    set "_eng=!aeng%%i!"
    set "_nm=!aname%%i!"
    set "_tag="
    if not "!_eng!"=="hex" if not "!_eng!"=="b32" if not "!_eng!"=="b64" if not "!_eng!"=="b85" (
        set "_tag= ^(fp:!_fp!^)"
    )
    powershell -NoProfile -Command ^
        "$b=[int]'!_b!';$sz=[int64]'!_sz!';$lg=[Math]::Log($b,2);" ^
        "$chars=[Math]::Ceiling($sz*8/$lg);" ^
        "Write-Host ('  [%%i] '+('!_nm!!_tag!').PadRight(30)+' b'+[string]$b+'  ~'+$chars+' chars')"
)
echo.
echo   [L]  Manage library
echo   [A]  Analyze sizes
echo   [Q]  Quit
echo  ============================================================
echo.
set "choice="
set /p "choice=Select alphabet: "

if /i "!choice!"=="q" exit /b
if /i "!choice!"=="l" goto :manage_lib
if /i "!choice!"=="a" goto :analyze

set "alph_idx=0"
for /l %%i in (1,1,!alphcount!) do (
    if "!choice!"=="%%i" set "alph_idx=%%i"
)
if "!alph_idx!"=="0" ( echo [ERROR] Invalid choice. & pause & goto :menu_alph )

set "sel_id=!aid%alph_idx%!"
set "sel_name=!aname%alph_idx%!"
set "sel_base=!abase%alph_idx%!"
set "sel_fp=!afp%alph_idx%!"
set "sel_eng=!aeng%alph_idx%!"

:menu_enc
cls
echo.
echo  ============================================================
echo          SOVEREIGN ENCODE
echo  ============================================================
echo   File    : !src_name!!src_ext!  ^(!srcbytes! bytes^)
echo   Alphabet: !sel_name!  b!sel_base!  fp:!sel_fp!
echo  ============================================================
echo.
echo   ENCRYPTION:
echo   [1]  None  ^(raw encode, no password^)
echo   [2]  Salted AES-256  ^(recommended^)
echo   [3]  No-salt AES-256
echo.
echo   SAFETY OPTIONS:
if "!sv_selfdesc!"=="1"   ( echo   [S]  Self-describing header  [ON] ) else ( echo   [S]  Self-describing header  [off] )
if "!sv_selfdesc!"=="1"   ( echo   [F]  Fingerprint size        [!sv_fpsize!]  ^(0=none, 2=short, 8=full^) ) else ( echo   [F]  Fingerprint size        [n/a]  ^(enable header first^) )
if "!sv_dualverify!"=="1" ( echo   [D]  Dual hex cross-verify   [ON] ) else ( echo   [D]  Dual hex cross-verify   [off] )
echo.
echo   [B]  Back to alphabet selection
echo  ============================================================
echo.
set "choice2="
set /p "choice2=Select: "

if /i "!choice2!"=="b" goto :menu_alph
if /i "!choice2!"=="s" (
    if "!sv_selfdesc!"=="0" ( set "sv_selfdesc=1" ) else ( set "sv_selfdesc=0" )
    goto :menu_enc
)
if /i "!choice2!"=="f" (
    if "!sv_selfdesc!"=="0" ( echo  [NOTE] Enable self-describing header first ^([S]^). & pause & goto :menu_enc )
    if "!sv_fpsize!"=="8" ( set "sv_fpsize=2" ) else if "!sv_fpsize!"=="2" ( set "sv_fpsize=0" ) else ( set "sv_fpsize=8" )
    goto :menu_enc
)
if /i "!choice2!"=="d" (
    if "!sv_dualverify!"=="0" ( set "sv_dualverify=1" ) else ( set "sv_dualverify=0" )
    goto :menu_enc
)
if "!choice2!"=="1" ( set "enc_mode=none"   & goto :do_encode )
if "!choice2!"=="2" ( set "enc_mode=salt"   & goto :ask_pass )
if "!choice2!"=="3" ( set "enc_mode=nosalt" & goto :ask_pass )
echo [ERROR] Invalid choice. & pause & goto :menu_enc

:ask_pass
set "vbs=!temp!\sv_pass.vbs"
echo pass = InputBox("Set encryption password:", "Sovereign") : WScript.StdOut.Write pass > "!vbs!"
set "pass="
for /f "tokens=*" %%A in ('cscript //nologo "!vbs!"') do set "pass=%%A"
del "!vbs!" 2>nul
if "!pass!"=="" ( echo [CANCELLED] & pause & goto :menu_enc )

set "vbs2=!temp!\sv_pass2.vbs"
echo pass = InputBox("Confirm password:", "Sovereign") : WScript.StdOut.Write pass > "!vbs2!"
set "pass2="
for /f "tokens=*" %%A in ('cscript //nologo "!vbs2!"') do set "pass2=%%A"
del "!vbs2!" 2>nul
if "!pass2!"=="" ( echo [CANCELLED] & pause & goto :menu_enc )
if not "!pass!"=="!pass2!" ( echo [ERROR] Passwords do not match. & pause & goto :menu_enc )
goto :do_encode

:do_encode
if "!enc_mode!"=="none" (
    set "outfile=!src_name!!src_ext!.!sel_id!"
) else (
    set "outfile=!src_name!!src_ext!.sv!sel_id!"
)

echo.
echo  Encoding...

:: Build args list
set "ps_args=-Mode Encode"
set "ps_args=!ps_args! -InFile "!src!""
set "ps_args=!ps_args! -OutFile "!outfile!""
set "ps_args=!ps_args! -AlphId !sel_id!"
set "ps_args=!ps_args! -LibFile "!libfile!""
if not "!enc_mode!"=="none" (
    set "ps_args=!ps_args! -Password "!pass!" -Salt !enc_mode!"
)
if "!sv_selfdesc!"=="1"   set "ps_args=!ps_args! -SelfDesc -FpSize !sv_fpsize!"
if "!sv_dualverify!"=="1" set "ps_args=!ps_args! -DualVerify"

powershell -NoProfile -ExecutionPolicy Bypass -File "!core!" !ps_args! > "!temp!\sv_result.tmp" 2>&1

set "ok=0" & set "chars=?" & set "keycard=" & set "dualok="
for /f "tokens=1,* delims=:" %%A in ('type "!temp!\sv_result.tmp"') do (
    if "%%A"=="OK"           set "ok=1"
    if "%%A"=="Chars"        set "chars=%%B"
    if "%%A"=="KeyCard"      set "keycard=%%B"
    if "%%A"=="DualVerified" set "dualok=%%B"
    if "%%A"=="ERROR"        echo  [ERROR] %%B
)
del "!temp!\sv_result.tmp" 2>nul

if "!ok!"=="0" ( echo  [FAILED] & pause & goto :menu_alph )

powershell -NoProfile -Command "[IO.File]::ReadAllText('!outfile!') | Set-Clipboard" 2>nul

echo.
echo  ============================================================
if not "!dualok!"=="" echo   [DUAL-VERIFIED] Hex cross-check passed
echo   [OK] File     : !outfile!
echo   [OK] Length   : !chars! characters
echo   [OK] Clipboard: copied
if not "!keycard!"=="" (
    echo   [OK] Key card : !keycard!
    echo  ============================================================
    echo.
    echo  ************************************************************
    echo  *  IMPORTANT: A key card was generated for this alphabet.  *
    echo  *  This is your ONLY recovery method if sv_lib.json and    *
    echo  *  the .svlib file are both lost.                          *
    echo  *                                                          *
    echo  *  PRINT IT or store it with medical/estate documents.     *
    echo  *  Without the key card, a custom alphabet encode is       *
    echo  *  PERMANENTLY UNRECOVERABLE.                              *
    echo  ************************************************************
) else (
    echo  ============================================================
)
pause & goto :menu_alph

:manage_lib
cls
echo.
echo  ============================================================
echo   ALPHABET LIBRARY  ^(!libfile!^)
echo  ============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "!core!" -Mode ListLib -LibFile "!libfile!" | ^
    powershell -NoProfile -Command "$i=0;$input|%%{$i++;$p=$_.Split([char]9);Write-Host ('  ['+$i+'] '+$p[1].PadRight(22)+' b'+$p[2].PadRight(5)+' fp:'+$p[3])}"
echo.
echo  To add a custom alphabet: open legacy\sovereign_alphabet_editor_v2.html,
echo  build your alphabet, click Save to Library, then drag the .svlib
echo  file onto legacy\scripts\sv_import.bat.
echo  ^(Or use the modern GUI: launch sovereign_gui.py and open the Editor tab.^)
echo.
echo  [B] Back
echo  ============================================================
echo.
set "lc=" & set /p "lc=: "
if /i "!lc!"=="b" goto :menu_alph
goto :manage_lib

:analyze
cls
echo.
echo  File: !src_name!!src_ext!  ^(!srcbytes! bytes^)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "!core!" -Mode ListLib -LibFile "!libfile!" | ^
    powershell -NoProfile -Command ^
        "$sz=[int64]'!srcbytes!';" ^
        "Write-Host ('  '+('Alphabet').PadRight(24)+('Base').PadRight(8)+('Raw').PadRight(16)+'Encrypted+Salted');" ^
        "Write-Host ('  '+'-'*60);" ^
        "$input|%%{$p=$_.Split([char]9);$b=[int]$p[2];$lg=[Math]::Log($b,2);$r=[Math]::Ceiling($sz*8/$lg);$s=[Math]::Ceiling(($sz+16)*8/$lg);Write-Host ('  '+$p[1].PadRight(24)+('b'+$b).PadRight(8)+[string]$r.PadRight(16)+$s)}"
echo.
pause & goto :menu_alph
