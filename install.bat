@echo off
setlocal enabledelayedexpansion

echo =========================================
echo  Deezer API Installer Script for Windows
echo =========================================

:: Find Python executable
set "PYTHON_CMD="
for %%x in (py python python3) do (
    %%x --version >nul 2>&1
    IF !ERRORLEVEL! EQU 0 (
        set "PYTHON_CMD=%%x"
        goto :found_python
    )
)

:found_python
IF NOT DEFINED PYTHON_CMD (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3 from https://www.python.org/ and try again.
    pause
    exit /b 1
)

echo [INFO] Found Python: %PYTHON_CMD%

:: Check for virtual environment
IF NOT EXIST "venv\Scripts\activate.bat" (
    echo [INFO] Creating Python virtual environment...
    %PYTHON_CMD% -m venv venv
    IF !ERRORLEVEL! NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [INFO] Virtual environment created successfully.
) ELSE (
    echo [INFO] Virtual environment already exists.
)

:: Activate virtual environment and install requirements
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

echo [INFO] Installing/Updating dependencies...
pip install --upgrade pip
pip install -r requirements.txt
IF !ERRORLEVEL! NEQ 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [INFO] Dependencies installed successfully.

:: Copy env template if not exists
IF NOT EXIST ".env" (
    echo [INFO] Creating .env file from template...
    copy .env.example .env >nul
    echo.
    echo *============================================================*
    echo  [ATTENTION] A new .env configuration file has been created.
    echo  Please open .env and enter your DEEZER_TOKEN ARL cookie.
    echo *============================================================*
    echo.
) ELSE (
    echo [INFO] .env configuration file already exists.
)

echo [SUCCESS] Installation complete! You can now start the server with start.bat.
pause
