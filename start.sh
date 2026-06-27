#!/bin/bash

echo "========================================="
echo " Deezer API Setup and Startup Script"
echo "========================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 is not installed or not in your PATH."
    echo "Please install Python 3 and try again."
    exit 1
fi

# Check for virtual environment
if [ ! -f "venv/bin/activate" ]; then
    echo "[INFO] Creating Python virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment."
        exit 1
    fi
fi

# Activate virtual environment
echo "[INFO] Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "[INFO] Installing/Updating dependencies..."
pip install -r requirements.txt --quiet
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install dependencies."
    exit 1
fi

# Handle .env file
if [ ! -f ".env" ]; then
    echo "[INFO] .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo ""
    echo "************************************************************"
    echo "[ATTENTION] A new .env file has been created."
    echo "Please open the .env file and set your DEEZER_TOKEN and API_KEY."
    echo "The server will still attempt to start with default values."
    echo "************************************************************"
    echo ""
    read -p "Press enter to continue..."
fi

# Start the server
echo "[INFO] Starting the server..."
python3 main.py
