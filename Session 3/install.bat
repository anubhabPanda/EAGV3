@echo off
echo ====================================
echo AI Character Designer - Installation
echo ====================================
echo.

echo [1/3] Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo [2/3] Generating extension icons...
python generate_icons.py
if errorlevel 1 (
    echo ERROR: Failed to generate icons
    pause
    exit /b 1
)
echo.

echo [3/3] Checking environment file...
if not exist .env (
    echo WARNING: .env file not found!
    echo Please create .env file from .env.example and add your Gemini API key
    echo.
    copy .env.example .env
    echo Created .env file. Please edit it and add your API key.
) else (
    echo .env file exists.
)
echo.

echo ====================================
echo Installation Complete!
echo ====================================
echo.
echo Next steps:
echo 1. Edit .env file and add your Gemini API key
echo 2. Start the server with: start_server.bat
echo 3. Load extension in Chrome (chrome://extensions/)
echo.
pause
