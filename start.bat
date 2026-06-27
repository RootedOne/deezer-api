@echo off
setlocal enabledelayedexpansion

echo =========================================
echo  Deezer API Setup and Startup Script
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
    echo Please install Python 3 and try again.
    pause
    exit /b 1
)

:: Check for virtual environment
IF NOT EXIST "venv\Scripts\activate.bat" (
    echo [INFO] Creating Python virtual environment using %PYTHON_CMD%...
    %PYTHON_CMD% -m venv venv
    IF !ERRORLEVEL! NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

:: Install requirements
echo [INFO] Installing/Updating dependencies...
pip install -r requirements.txt --quiet
IF !ERRORLEVEL! NEQ 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Handle .env file
IF NOT EXIST ".env" (
    echo [INFO] .env file not found. Creating from .env.example...
    copy .env.example .env >nul
    echo.
    echo ************************************************************
    echo [ATTENTION] A new .env file has been created.
    echo Please open the .env file and set your DEEZER_TOKEN and API_KEY.
    echo The server will still attempt to start with default values.
    echo ************************************************************
    echo.
    pause
)

:: Start the server
echo [INFO] Starting the server...
python main.py

pause
