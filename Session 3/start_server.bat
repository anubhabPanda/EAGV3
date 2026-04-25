@echo off
echo ====================================
echo AI Character Designer - Starting Server
echo ====================================
echo.

echo Checking for .env file...
if not exist .env (
    echo ERROR: .env file not found!
    echo Please run install.bat first or create .env file manually.
    pause
    exit /b 1
)

echo Starting Flask server on http://localhost:5001
echo.
echo Keep this window open while using the extension!
echo Press Ctrl+C to stop the server.
echo.
echo ====================================
echo.

python server.py

pause
