@echo off
setlocal

:: ── 원본 경로 (Codex CLI 글로벌)
set CODEX_DEST=%USERPROFILE%\.codex\skills\weekly-analysis
set SKILL_ORIG=%CODEX_DEST%\SKILL.md

:: ── 스크립트 위치 기준으로 소스 경로 계산
set SCRIPT_DIR=%~dp0
set SKILL_SRC=%SCRIPT_DIR%weekly-analysis\SKILL.md

:: ── 1. Codex CLI 글로벌에 원본 배치
if not exist "%CODEX_DEST%" mkdir "%CODEX_DEST%"
copy /Y "%SKILL_SRC%" "%SKILL_ORIG%" >nul
echo [OK] 원본 -^> %SKILL_ORIG%

:: ── 2. symlink 생성 함수 (mklink /H = 하드링크, 관리자 불필요 대안)
::     심볼릭링크(mklink) 실패 시 하드링크(mklink /H)로 폴백
call :make_link "%USERPROFILE%\.claude\skills\weekly-analysis\SKILL.md"
call :make_link "%USERPROFILE%\.gemini\skills\weekly-analysis\SKILL.md"

:: ── 3. Claude Code 프로젝트 레벨 (.claude는 스크립트 위치 기준 두 단계 위)
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_ROOT=%%~fI
call :make_link "%PROJECT_ROOT%\.claude\skills\weekly-analysis\SKILL.md"

echo.
echo 설치 완료. SKILL 수정 시 아래 파일만 편집하면 됩니다.
echo %SKILL_ORIG%
goto :eof

:: ── 심볼릭링크 생성 서브루틴
:make_link
set TARGET=%~1
set TARGET_DIR=%~dp1
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"
if exist "%TARGET%" del /F /Q "%TARGET%"
mklink "%TARGET%" "%SKILL_ORIG%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] symlink -^> %TARGET%
) else (
    mklink /H "%TARGET%" "%SKILL_ORIG%" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] hardlink -^> %TARGET%
    ) else (
        echo [WARN] 링크 생성 실패, 파일 복사로 대체: %TARGET%
        copy /Y "%SKILL_ORIG%" "%TARGET%" >nul
    )
)
goto :eof