@echo off
chcp 65001 >nul
echo ========================================
echo  Pushing Textile Traceability to GitHub
echo ========================================
echo.

cd /d "%~dp0"

echo [1/8] Configuring git identity...
git config user.email "sephilon.trading@gmail.com"
git config user.name "Sephilon Dinh"

echo [2/8] Checking git...
git --version

echo [3/8] Initializing git repository...
if not exist ".git" (
    git init
) else (
    echo    Git repo already exists, skipping init.
)

echo [4/8] Adding all files...
git add .

echo [5/8] Creating commit...
git commit -m "Initial commit: Textile Traceability System"

echo [6/8] Setting branch to main...
git branch -M main

echo [7/8] Setting remote origin...
git remote remove origin 2>nul
git remote add origin https://github.com/duyprime1993/textile-traceability.git

echo [8/8] Pushing to GitHub...
echo    (A browser window may open for GitHub authentication)
echo    (Please sign in if prompted)
echo.
git push -u origin main

echo.
echo ========================================
if %ERRORLEVEL% EQU 0 (
    echo  SUCCESS! Code pushed to GitHub!
    echo  Repo: https://github.com/duyprime1993/textile-traceability
) else (
    echo  Push may have failed. Check errors above.
)
echo ========================================
echo.
pause
