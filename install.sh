#!/usr/bin/env bash

# ==========================================
# Deezer API Interactive Management Script
# ==========================================

# Exit on error for safety, but handle custom error flows
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

PROJECT_DIR="$(pwd)"
SERVICE_NAME="deezer-api.service"

# OS Detection
IS_LINUX=false
if [ "$(uname)" = "Linux" ]; then
    IS_LINUX=true
fi

# Print Header
print_header() {
    clear 2>/dev/null || true
    echo -e "${PURPLE}===================================================${NC}"
    echo -e "${BOLD}${CYAN}          Deezer API Management Installer          ${NC}"
    echo -e "${PURPLE}===================================================${NC}"
}

# Check if running on Linux before calling systemd/apt commands
assert_linux() {
    if [ "$IS_LINUX" = false ]; then
        echo -e "${RED}Error: This option requires Linux (Ubuntu/Debian) and systemd.${NC}"
        echo -e "Current system is: $(uname)"
        echo -ne "\nPress Enter to return to the main menu..."
        read -r
        return 1
    fi
}

# Helper to lookup current value in .env
get_current_val() {
    local key="$1"
    local default_val="$2"
    if [ -f .env ]; then
        local val
        val=$(grep -E "^${key}=" .env | head -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
        if [ -n "$val" ]; then
            echo "$val"
            return
        fi
    fi
    echo "$default_val"
}

# Prompt and update .env file
configure_env() {
    echo -e "\n=== Configuring Environment Variables ==="
    if [ ! -f .env.example ]; then
        echo -e "${RED}Error: .env.example not found! Cannot generate .env.${NC}"
        return 1
    fi

    # Save original stdin (descriptor 0) to descriptor 3
    exec 3<&0

    local temp_env=".env.tmp"
    rm -f "$temp_env"
    
    local comment=""
    while IFS= read -r line || [ -n "$line" ]; do
        # Trim leading/trailing whitespace
        local trimmed
        trimmed=$(echo "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
        
        # Empty line
        if [ -z "$trimmed" ]; then
            echo "" >> "$temp_env"
            comment=""
            continue
        fi
        
        # Comment line
        if [[ "$trimmed" =~ ^# ]]; then
            echo "$line" >> "$temp_env"
            # Accumulate comment for prompting
            comment="${comment}\n${trimmed}"
            continue
        fi
        
        # Variable line (KEY=VAL)
        if [[ "$trimmed" =~ ^([A-Za-z0-9_]+)=(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local default_val="${BASH_REMATCH[2]}"
            
            # Strip trailing comment on the same line if present, and strip quotes/spaces
            default_val=$(echo "$default_val" | cut -d'#' -f1 | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
            
            # Get current value from existing .env if present, otherwise use default
            local current_val
            current_val=$(get_current_val "$key" "$default_val")
            
            # Display accumulated comment/description
            if [ -n "$comment" ]; then
                echo -e "${CYAN}${comment}${NC}"
            fi
            
            # Prompt user using saved stdin (FD 3)
            echo -ne "${BOLD}${key}${NC} [Default: ${GREEN}${current_val}${NC}]: "
            read -r user_val <&3
            
            # If user pressed enter, use current/default value
            if [ -z "$user_val" ]; then
                user_val="$current_val"
            fi
            
            # Write to temporary env file
            echo "${key}=\"${user_val}\"" >> "$temp_env"
            comment=""
            echo ""
        else
            # If it's something else, write it as is
            echo "$line" >> "$temp_env"
        fi
    done < .env.example
    
    # Close descriptor 3
    exec 3<&-

    mv "$temp_env" .env
    echo -e "${GREEN}Environment file (.env) successfully updated!${NC}"
}

# Option 1: Install
install_api() {
    assert_linux || return 0

    print_header
    echo -e "${YELLOW}Starting Deezer API Installation...${NC}"

    # 1. System Dependencies
    echo -e "\n--- Step 1: Checking and installing system dependencies ---"
    local install_needed=false
    for pkg in python3 python3-pip python3-venv git curl; do
        if ! dpkg -s "$pkg" >/dev/null 2>&1; then
            echo -e "${YELLOW}Dependency $pkg is missing.${NC}"
            install_needed=true
        fi
    done
    
    if [ "$install_needed" = true ]; then
        echo -e "Updating package lists and installing dependencies..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv git curl
    else
        echo -e "${GREEN}All system dependencies are already installed.${NC}"
    fi

    # 2. Virtual Environment Setup
    echo -e "\n--- Step 2: Setting up Python virtual environment ---"
    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment in .venv..."
        python3 -m venv .venv
    fi
    echo "Upgrading pip and installing requirements..."
    ./.venv/bin/pip install --upgrade pip
    ./.venv/bin/pip install -r requirements.txt

    # 3. Environment Config (.env)
    echo -e "\n--- Step 3: Configuring environment variables ---"
    configure_env

    # 4. Systemd Service Setup
    echo -e "\n--- Step 4: Configuring systemd service ---"
    local run_user
    run_user=$(whoami)
    local run_group
    run_group=$(id -gn)

    echo "Creating systemd service file at /etc/systemd/system/${SERVICE_NAME}..."
    sudo tee "/etc/systemd/system/${SERVICE_NAME}" > /dev/null <<EOF
[Unit]
Description=Deezer API Service
After=network.target

[Service]
Type=simple
User=${run_user}
Group=${run_group}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PROJECT_DIR}/.venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PATH=${PROJECT_DIR}/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

    echo "Reloading systemd daemon..."
    sudo systemctl daemon-reload
    echo "Enabling and starting service ${SERVICE_NAME}..."
    sudo systemctl enable "${SERVICE_NAME}"
    sudo systemctl restart "${SERVICE_NAME}"

    echo -e "\n${GREEN}Installation Completed Successfully!${NC}"
    echo -e "Checking service status:"
    sudo systemctl status "${SERVICE_NAME}" --no-pager

    echo -ne "\nPress Enter to return to the main menu..."
    read -r
}

# Option 2: Update bot using latest git project files
update_bot() {
    print_header
    echo -e "${YELLOW}Checking Git repository status...${NC}"
    
    if [ ! -d .git ]; then
        echo -e "${RED}Error: This directory is not a Git repository.${NC}"
        echo -ne "\nPress Enter to return to the main menu..."
        read -r
        return 0
    fi

    # Check for local changes
    if [ -n "$(git status --porcelain)" ]; then
        echo -e "${YELLOW}Local changes detected!${NC}"
        echo "Please select how you'd like to handle them:"
        echo "1) Stash changes (Save them temporarily to apply/view later)"
        echo "2) Discard changes (Perform a hard reset to match remote)"
        echo "3) Cancel update"
        echo -n "Select option [1-3]: "
        read -r git_opt
        
        case "$git_opt" in
            1)
                echo "Stashing changes..."
                git stash
                ;;
            2)
                echo "Discarding all local modifications..."
                git reset --hard
                ;;
            *)
                echo "Update cancelled."
                echo -ne "\nPress Enter to return to the main menu..."
                read -r
                return 0
                ;;
        esac
    fi

    # Pull changes
    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    echo -e "\nPulling latest changes from origin/${current_branch}..."
    git pull origin "${current_branch}"

    # Re-install dependencies if virtual env exists
    if [ -d ".venv" ]; then
        echo -e "\nUpdating dependencies inside virtual environment..."
        ./.venv/bin/pip install -r requirements.txt
    else
        echo -e "${YELLOW}Virtual environment (.venv) not found. Skipping pip dependencies reinstall.${NC}"
    fi

    # Restart service if Linux & systemd service is active/configured
    if [ "$IS_LINUX" = true ] && [ -f "/etc/systemd/system/${SERVICE_NAME}" ]; then
        echo -e "\nRestarting service ${SERVICE_NAME}..."
        sudo systemctl restart "${SERVICE_NAME}"
        echo -e "${GREEN}Service restarted successfully!${NC}"
    fi

    echo -e "\n${GREEN}Update completed!${NC}"
    echo -ne "\nPress Enter to return to the main menu..."
    read -r
}

# Option 3: Check logs
check_logs() {
    assert_linux || return 0

    while true; do
        print_header
        echo -e "${YELLOW}=== Service Logs ===${NC}"
        echo "1) View last 50 lines of logs"
        echo "2) Stream logs live (Press Ctrl+C to return)"
        echo "3) Return to main menu"
        echo -ne "\nSelect option [1-3]: "
        read -r log_opt
        
        case "$log_opt" in
            1)
                echo -e "\n--- Last 50 Log Lines ---"
                sudo journalctl -n 50 -u "${SERVICE_NAME}" --no-pager
                echo -ne "\nPress Enter to return..."
                read -r
                ;;
            2)
                echo -e "\n--- Streaming Logs (Press Ctrl+C to exit) ---"
                # Temporarily trap SIGINT in this shell to prevent script termination
                trap '' INT
                sudo journalctl -f -u "${SERVICE_NAME}"
                trap - INT
                ;;
            3)
                break
                ;;
            *)
                echo -e "${RED}Invalid option.${NC}"
                sleep 1
                ;;
        esac
    done
}

# Option 4: Update .env
update_env() {
    print_header
    configure_env

    # Prompt to restart if running
    if [ "$IS_LINUX" = true ] && [ -f "/etc/systemd/system/${SERVICE_NAME}" ]; then
        echo -ne "\nWould you like to restart the ${SERVICE_NAME} service to apply changes? [y/N]: "
        read -r rs_opt
        if [[ "$rs_opt" =~ ^[Yy]$ ]]; then
            sudo systemctl restart "${SERVICE_NAME}"
            echo -e "${GREEN}Service restarted!${NC}"
        fi
    fi

    echo -ne "\nPress Enter to return to the main menu..."
    read -r
}

# Option 5: Fully remove
remove_api() {
    assert_linux || return 0

    print_header
    echo -e "${RED}${BOLD}=== WARNING: FULL REMOVAL ===${NC}"
    echo -e "This will stop/remove the service, delete the Python virtual environment (.venv),"
    echo -e "and optionally delete the entire project folder."
    echo -ne "\nAre you sure you want to proceed? [y/N]: "
    read -r confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Removal cancelled."
        sleep 1
        return 0
    fi

    echo -e "\nStopping and disabling service ${SERVICE_NAME}..."
    sudo systemctl stop "${SERVICE_NAME}" || true
    sudo systemctl disable "${SERVICE_NAME}" || true

    echo "Removing systemd service file..."
    sudo rm -f "/etc/systemd/system/${SERVICE_NAME}"
    sudo systemctl daemon-reload
    sudo systemctl reset-failed || true

    if [ -d ".venv" ]; then
        echo "Removing Python virtual environment..."
        rm -rf .venv
    fi

    if [ -d "tmp" ]; then
        echo "Cleaning up temporary downloads..."
        rm -rf tmp/public_downloads/* || true
    fi

    echo -e "${GREEN}Service and virtual environment removed successfully.${NC}"
    
    echo -ne "\nWould you like to delete the entire project directory (${PROJECT_DIR})? [y/N]: "
    read -r del_dir
    if [[ "$del_dir" =~ ^[Yy]$ ]]; then
        echo "Deleting directory and exiting..."
        cd ..
        rm -rf "${PROJECT_DIR}"
        exit 0
    fi

    echo -ne "\nPress Enter to return to the main menu..."
    read -r
}

# Main Loop
while true; do
    print_header
    if [ "$IS_LINUX" = false ]; then
        echo -e "${YELLOW}Warning: Running on non-Linux environment ($(uname)). Some options will be restricted.${NC}\n"
    fi
    echo "1) Install"
    echo "2) Update bot using latest git project files"
    echo "3) Check logs"
    echo "4) Update .env"
    echo "5) Fully remove"
    echo "6) Exit"
    echo -ne "\nSelect option [1-6]: "
    read -r opt
    
    case "$opt" in
        1)
            install_api
            ;;
        2)
            update_bot
            ;;
        3)
            check_logs
            ;;
        4)
            update_env
            ;;
        5)
            remove_api
            ;;
        6)
            echo -e "\nExiting. Goodbye!"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option. Please try again.${NC}"
            sleep 1
            ;;
    esac
done
