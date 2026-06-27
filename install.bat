@echo off
setlocal enabledelayedexpansion

:: ==========================================
:: Deezer API Interactive Management Script
:: ==========================================

:: Colors emulation for Windows (Requires Windows 10+ for ANSI escape codes)
:: We define them here, but we will print them normally or use color commands where suitable.
set "ESC="
set "RED=%ESC%[0;31m"
set "GREEN=%ESC%[0;32m"
set "YELLOW=%ESC%[0;33m"
set "BLUE=%ESC%[0;34m"
set "PURPLE=%ESC%[0;35m"
set "CYAN=%ESC%[0;36m"
set "BOLD=%ESC%[1m"
set "NC=%ESC%[0m"

set "PROJECT_DIR=%CD%"

:MAIN_LOOP
call :print_header
echo 1) Install
echo 2) Update bot using latest git project files
echo 3) Check logs
echo 4) Update .env
echo 5) Fully remove
echo 6) Exit
echo.
set /p "opt=Select option [1-6]: "

if "%opt%"=="1" (
    call :install_api
    goto MAIN_LOOP
)
if "%opt%"=="2" (
    call :update_bot
    goto MAIN_LOOP
)
if "%opt%"=="3" (
    call :check_logs
    goto MAIN_LOOP
)
if "%opt%"=="4" (
    call :update_env
    goto MAIN_LOOP
)
if "%opt%"=="5" (
    call :remove_api
    goto MAIN_LOOP
)
if "%opt%"=="6" (
    echo.
    echo Exiting. Goodbye!
    exit /b 0
)

echo %RED%Invalid option. Please try again.%NC%
timeout /t 1 >nul
goto MAIN_LOOP


:print_header
cls 2>nul
echo %PURPLE%===================================================%NC%
echo %BOLD%%CYAN%          Deezer API Management Installer          %NC%
echo %PURPLE%===================================================%NC%
exit /b 0


:configure_env
echo.
echo === Configuring Environment Variables ===
if not exist ".env.example" (
    echo %RED%Error: .env.example not found! Cannot generate .env.%NC%
    exit /b 1
)

:: Create or clear .env.tmp
type nul > .env.tmp

for /f "tokens=*" %%l in (.env.example) do (
    set "line=%%l"
    set "first_char=!line:~0,1!"
    
    if "!line!"=="" (
        echo.>> .env.tmp
    ) else if "!first_char!"=="#" (
        echo !line!>> .env.tmp
        echo %CYAN%!line!%NC%
    ) else (
        :: KEY=VALUE line
        for /f "tokens=1* delims==" %%a in ("!line!") do (
            set "key=%%a"
            set "default_val=%%b"
            
            :: Clean key and default value spaces/quotes
            for /f "tokens=* delims= " %%k in ("!key!") do set "key=%%k"
            for /f "tokens=* delims= " %%v in ("!default_val!") do set "default_val=%%v"
            
            :: Remove trailing comments on same line if any
            for /f "tokens=1 delims=#" %%c in ("!default_val!") do set "default_val=%%c"
            
            :: Strip trailing spaces
            for /l %%i in (1,1,5) do (
                if "!default_val:~-1!"==" " set "default_val=!default_val:~0,-1!"
            )
            :: Strip surrounding quotes
            if "!default_val:~0,1!"=="""" set "default_val=!default_val:~1,-1!"
            if "!default_val:~0,1!"=="'" set "default_val=!default_val:~1,-1!"
            
            :: Check if KEY already exists in current .env
            set "current_val=!default_val!"
            if exist ".env" (
                for /f "tokens=1* delims==" %%x in ('findstr /I /R "^!key!=" .env 2^>nul') do (
                    set "val=%%y"
                    if not "!val!"=="" (
                        :: Clean quotes/spaces
                        for /f "tokens=* delims= " %%w in ("!val!") do set "val=%%w"
                        if "!val:~0,1!"=="""" set "val=!val:~1,-1!"
                        if "!val:~0,1!"=="'" set "val=!val:~1,-1!"
                        set "current_val=!val!"
                    )
                )
            )
            
            :: Prompt user
            set "user_val="
            set /p "user_val=%BOLD%!key!%NC% [Default: %GREEN%!current_val!%NC%]: "
            if "!user_val!"=="" set "user_val=!current_val!"
            
            echo !key!="!user_val!">> .env.tmp
            echo.
        )
    )
)

move /y .env.tmp .env >nul
echo %GREEN%Environment file (.env) successfully updated!%NC%
exit /b 0


:install_api
call :print_header
echo %YELLOW%Starting Deezer API Installation...%NC%

:: 1. System Dependencies (Find Python)
echo.
echo --- Step 1: Checking and installing system dependencies ---
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
    echo %RED%[ERROR] Python is not installed or not in your PATH.%NC%
    echo Please install Python 3 and try again.
    pause
    exit /b 1
)
echo %GREEN%Python is installed: %PYTHON_CMD%%NC%

:: 2. Virtual Environment Setup
echo.
echo --- Step 2: Setting up Python virtual environment ---
IF NOT EXIST "venv\Scripts\activate.bat" (
    echo Creating virtual environment in venv...
    %PYTHON_CMD% -m venv venv
    IF !ERRORLEVEL! NEQ 0 (
        echo %RED%[ERROR] Failed to create virtual environment.%NC%
        pause
        exit /b 1
    )
)
echo Upgrading pip and installing requirements...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
IF !ERRORLEVEL! NEQ 0 (
    echo %RED%[ERROR] Failed to install dependencies.%NC%
    pause
    exit /b 1
)

:: 3. Environment Config (.env)
echo.
echo --- Step 3: Configuring environment variables ---
call :configure_env

:: 4. Windows Service warning (systemd equivalent)
echo.
echo --- Step 4: Windows Service Setup Info ---
echo [INFO] systemd service daemon setup is Linux-only.
echo To run the backend on Windows, simply use start.bat or
echo configure a Task Scheduler task to run start.bat on startup.

echo.
echo %GREEN%Installation Completed Successfully!%NC%
echo.
set /p "dummy=Press Enter to return to the main menu..."
exit /b 0


:update_bot
call :print_header
echo %YELLOW%Checking Git repository status...%NC%

if not exist ".git" (
    echo %RED%Error: This directory is not a Git repository.%NC%
    set /p "dummy=Press Enter to return to the main menu..."
    exit /b 0
)

:: Check local changes
set "local_changes="
for /f "tokens=*" %%i in ('git status --porcelain 2^>nul') do set "local_changes=%%i"

if not "%local_changes%"=="" (
    echo %YELLOW%Local changes detected!%NC%
    echo Please select how you'd like to handle them:
    echo 1) Stash changes (Save them temporarily to apply/view later)
    echo 2) Discard changes (Perform a hard reset to match remote)
    echo 3) Cancel update
    set /p "git_opt=Select option [1-3]: "
    
    if "!git_opt!"=="1" (
        echo Stashing changes...
        git stash
    ) else if "!git_opt!"=="2" (
        echo Discarding all local modifications...
        git reset --hard
    ) else (
        echo Update cancelled.
        set /p "dummy=Press Enter to return to the main menu..."
        exit /b 0
    )
)

:: Pull changes
for /f "tokens=*" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "current_branch=%%b"
echo.
echo Pulling latest changes from origin/%current_branch%...
git pull origin "%current_branch%"

:: Reinstall dependencies if venv exists
if exist "venv\Scripts\activate.bat" (
    echo.
    echo Updating dependencies inside virtual environment...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    echo %YELLOW%Virtual environment (venv) not found. Skipping pip dependencies reinstall.%NC%
)

echo.
echo %GREEN%Update completed!%NC%
set /p "dummy=Press Enter to return to the main menu..."
exit /b 0


:check_logs
call :print_header
echo %YELLOW%=== Service Logs ===%NC%
echo Windows does not support Linux systemd journalctl logging.
echo Please run the server in the command prompt using start.bat
echo to view live server logs.
echo.
set /p "dummy=Press Enter to return to the main menu..."
exit /b 0


:update_env
call :print_header
call :configure_env
echo.
set /p "dummy=Press Enter to return to the main menu..."
exit /b 0


:remove_api
call :print_header
echo %RED%%BOLD%=== WARNING: FULL REMOVAL ===%NC%
echo This will delete the Python virtual environment (venv)
echo and optionally delete the entire project folder.
echo.
set /p "confirm=Are you sure you want to proceed? [y/N]: "
if /i not "%confirm%"=="y" (
    echo Removal cancelled.
    timeout /t 2 >nul
    exit /b 0
)

if exist "venv" (
    echo Removing Python virtual environment...
    rmdir /s /q venv
)

if exist "tmp" (
    echo Cleaning up temporary downloads...
    del /f /q /s tmp\public_downloads\* >nul 2>&1
)

echo %GREEN%Virtual environment removed successfully.%NC%
echo.
set /p "del_dir=Would you like to delete the entire project directory (%PROJECT_DIR%)? [y/N]: "
if /i "%del_dir%"=="y" (
    echo Deleting directory and exiting...
    cd ..
    rmdir /s /q "%PROJECT_DIR%"
    exit 0
)

set /p "dummy=Press Enter to return to the main menu..."
exit /b 0
