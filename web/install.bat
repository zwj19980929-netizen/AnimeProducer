@echo off
echo Installing AnimeMatrix Web Frontend...
echo.

cd web
if not exist node_modules (
    echo Installing dependencies...
    call npm install
) else (
    echo Dependencies already installed.
)

echo.
echo Installation complete!
echo.
echo To start the development server, run:
echo   cd web
echo   npm run dev
echo.
pause
