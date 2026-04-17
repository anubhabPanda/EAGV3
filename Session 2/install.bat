@echo off
echo ========================================
echo Hotel Comparison Extension - Installer
echo ========================================
echo.

echo Step 1: Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo Step 2: Generating extension icons...
python generate_icons.py
if errorlevel 1 (
    echo WARNING: Icon generation had issues, but continuing...
)
echo.

echo Step 3: Checking for .env file...
if not exist .env (
    echo .env file not found!
    echo.
    echo Please create a .env file with your Gemini API key:
    echo GEMINI_API_KEY=your_api_key_here
    echo.
    echo You can copy .env.example and rename it to .env
    pause
) else (
    echo .env file found!
)
echo.

echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Make sure .env file has your GEMINI_API_KEY
echo 2. Load extension in Chrome (chrome://extensions/)
echo 3. Run: python server.py
echo.
echo See QUICKSTART.md for detailed instructions
echo.
pause
