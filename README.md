# Downloader REST API

[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/python-3.8+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos-lightgrey.svg?style=flat)](#setup--execution)
[![Status](https://img.shields.io/badge/status-active-green.svg?style=flat)](#)

A high-performance standalone REST API wrapper for the Telegram Music Downloader. It exposes secure endpoints using FastAPI to query search data and generate temporary download links for tracks and albums directly from Deezer.

---

## 🌟 Core Features

- **Concurrent Unified Search**: Concurrently queries tracks, albums, and artists using asynchronous worker threads to deliver unified search results rapidly.
- **Dynamic Quality Overrides**: Choose quality tiers (`flac`, `mp3`, `mp3_320`, `mp3_128`, or `auto`) per request via query parameters. Fallback logic automatically steps down to lower qualities if the requested tier is unavailable.
- **Resilient Multi-Account Cookie Rotation**: Configure multiple fallback ARL tokens. The download engine automatically detects authentication or retrieval errors at startup or runtime, rotating to the next available account transparently.
- **Self-Cleaning Storage**: An asynchronous background sweeper periodically cleans the public downloads cache directory, removing files older than a user-configured threshold.
- **Interactive Manager**: Includes a premium terminal-based command utility (`install.sh`) to install dependencies, manage env configurations, update the codebase, check logs, or uninstall the service.

---

## 📁 Directory Structure

```
.
├── install.sh         # Interactive service installer and manager script
├── main.py            # FastAPI entry point, endpoint routes & server loop
├── download.py        # Bot-independent track/album download controller
├── utils.py           # Shared utilities (temporary cache paths)
├── requirements.txt   # Python dependency list
├── .env.example       # Environment configuration template
├── .env               # Active configurations (generated, git-ignored)
├── test_api.py        # Mock integration test suite
├── dl_utils/          # Local search, download, and decryption libraries
└── tmp/
    └── public_downloads/ # Public web cache for downloaded files and ZIPs
```

---

## 🚀 Setup & Execution

### Option A: Automated Setup (Recommended)
We provide an interactive command-line installer for Linux (Ubuntu/Debian) that sets up the virtual environment, installs dependencies, prompts for configuration values, and configures a systemd background service.

To start the installer, execute:
```bash
./install.sh
```
Follow the interactive prompt menu:
1. **Install**: Installs system requirements, builds the Python virtual environment (`.venv`), prompts for environment variables, and enables/starts the systemd service.
2. **Update bot using latest git project files**: Fetches updates from Git (prompting to stash/discard local edits), reinstalls packages, and restarts the service.
3. **Check logs**: Views or streams live service logs (`journalctl`).
4. **Update .env**: Interactively modifies env values and restarts the service.
5. **Fully remove**: Disables/deletes systemd files, removes `.venv`, and optionally wipes the project directory.

### Option B: Manual Setup
If you are on macOS or wish to run the API manually:

1. **Install requirements** in your local environment or virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your favorite text editor
   ```

3. **Start the API server**:
   ```bash
   python3 main.py
   ```
   The API will listen at `http://localhost:8000`. Access the interactive Swagger documentation at `http://localhost:8000/docs`.

---

## ⚙️ Configuration Variables

The API loads configurations from the `.env` file at startup. Below are the available variables:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `API_KEY` | `dev-key` | Secret token passed in the `X-API-Key` header for authorization. |
| `API_HOST` | `0.0.0.0` | Host IP address the Uvicorn server binds to. |
| `API_PORT` | `8000` | Port number the Uvicorn server listens on. |
| `FILE_MAX_AGE_SEC` | `3600` | Expiration limit of download links (e.g. 1 hour) before purging. |
| `CLEANUP_INTERVAL_SEC` | `300` | Frequency in seconds (e.g. 5 minutes) of the cache cleanup loop. |
| `DEEZER_TOKEN_1` | *Required* | Primary Deezer ARL cookie used to authenticate downloads. |
| `DEEZER_TOKEN_2` | *Optional* | First backup Deezer ARL cookie for automatic failover. |
| `DEEZER_TOKEN_N` | *Optional* | Additional fallback tokens (`DEEZER_TOKEN_3`, `DEEZER_TOKEN_4`, etc.). |

---

## 📡 API Reference

All requests require authorization. Include the API key in your request headers:
```http
X-API-Key: <your-secret-api-token>
```

### Search Endpoints

| Endpoint | Method | Query Params | Description |
| :--- | :--- | :--- | :--- |
| `/api/search` | `GET` | `q` *(Required)* | Concurrent search returning tracks, albums, and artists. |
| `/api/search/tracks` | `GET` | `q` *(Required)* | Returns search results matching tracks only. |
| `/api/search/albums` | `GET` | `q` *(Required)* | Returns search results matching albums only. |
| `/api/search/artists` | `GET` | `q` *(Required)* | Returns search results matching artists only. |

#### Unified Search Example:
```bash
curl -H "X-API-Key: dev-key" "http://localhost:8000/api/search?q=comfortably+numb"
```
**Response (200 OK)**:
```json
{
  "query": "comfortably numb",
  "tracks": [
    {
      "id": "12345",
      "id_type": "track",
      "title": "Comfortably Numb",
      "img_url": "https://e-cdns-images.dzcdn.net/...",
      "album": "The Wall",
      "album_id": 999,
      "artist": "Pink Floyd",
      "preview_url": "https://..."
    }
  ],
  "albums": [],
  "artists": []
}
```

---

### Download Endpoints

| Endpoint | Method | Query Params | Description |
| :--- | :--- | :--- | :--- |
| `/api/download/track/{track_id}` | `GET` | `quality` *(Optional)* | Downloads a single track. Qualities: `flac`, `mp3`, `mp3_320`, `mp3_128`, `auto`. |
| `/api/download/album/{album_id}` | `GET` | `quality` *(Optional)* | Downloads all album tracks, zips them, and returns a download link. |

#### Download Track Example:
```bash
curl -H "X-API-Key: dev-key" "http://localhost:8000/api/download/track/12345?quality=flac"
```
**Response (200 OK)**:
```json
{
  "status": "success",
  "track_id": "12345",
  "title": "Comfortably Numb",
  "artist": "Pink Floyd",
  "album": "The Wall",
  "quality_used": "FLAC",
  "download_url": "http://localhost:8000/static/Pink_Floyd_-_Comfortably_Numb_12345.flac"
}
```

#### Download Album Example:
```bash
curl -H "X-API-Key: dev-key" "http://localhost:8000/api/download/album/999?quality=auto"
```
**Response (200 OK)**:
```json
{
  "status": "success",
  "album_id": "999",
  "title": "The Wall",
  "artist": "Pink Floyd",
  "track_count": 26,
  "quality_used": "MP3_320",
  "download_url": "http://localhost:8000/static/Pink_Floyd_-_The_Wall_999.zip"
}
```

---

## 🛠️ Architecture Details

### 🔄 Multi-Account ARL Fallback Rotation
To maximize service availability and circumvent single-account download rate limits or expiration:
1. **Startup Check**: On startup, the download controller parses the environment variables sequentially (`DEEZER_TOKEN_1`, `DEEZER_TOKEN_2`, etc.) and tests them. The first token to pass session initialization becomes the active token.
2. **Runtime Failover**: If a download fails due to decryption, permissions, or session blocks, the controller rotates to the next available token index and rebuilds the active download session.
3. **Transparent Recovery**: The current download is retried using the new session automatically. If all configured accounts fail, the endpoint returns a `500 Internal Server Error`.

### 🧹 Background Cache Sweeper
Downloaded media is temporarily stored in `tmp/public_downloads/` to serve as static assets. To avoid storage bloat:
- An asynchronous loop starts when the FastAPI app launches.
- Every `CLEANUP_INTERVAL_SEC` seconds, it scans the directory.
- Files with a modification time older than `FILE_MAX_AGE_SEC` are automatically unlinked.

---

## 🧪 Running Integration Tests

To run local mock integration tests that validate authentication, routing, download locks, zip structures, and format fallbacks:
```bash
python3 test_api.py
```
