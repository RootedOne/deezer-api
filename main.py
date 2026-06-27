import asyncio
import os
import sys
import time
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from contextlib import asynccontextmanager

# 1. Configure local import paths
import sys
from pathlib import Path
API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

# 2. Load API-specific local env configuration
from dotenv import load_dotenv
ENV_PATH = API_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Load token.env from local directory if present
LOCAL_TOKEN_ENV = API_DIR / "token.env"
if LOCAL_TOKEN_ENV.exists():
    load_dotenv(dotenv_path=LOCAL_TOKEN_ENV)

# FastAPI imports
from fastapi import FastAPI, Header, HTTPException, status, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# 3. Local module imports (completely isolated)
from utils import TMP_DIR
from dl_utils.deezer_utils import clean_filename
from dl_utils.deezer_download import (
    deezer_search,
    TYPE_TRACK,
    TYPE_ALBUM,
    TYPE_ARTIST,
)
import dl_utils.deezer_download as deezer_download
from download import download_track, download_album, DEFAULT_QUALITY

# Configure self-contained public downloads directory under api/tmp
PUBLIC_DOWNLOADS_DIR = API_DIR / "tmp" / "public_downloads"
PUBLIC_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Load API Key from environment or default for development
API_KEY = os.environ.get("API_KEY", "dev-key")
if API_KEY == "dev-key":
    print("WARNING: API_KEY environment variable not set. Using default 'dev-key' for authentication.")

# Lock to avoid concurrent quality modification race conditions
download_lock = asyncio.Lock()

async def cleanup_old_files():
    """Background task to delete downloaded files older than a threshold."""
    while True:
        try:
            now = time.time()
            max_age = int(os.environ.get("FILE_MAX_AGE_SEC", 3600))  # default 1 hour
            if PUBLIC_DOWNLOADS_DIR.exists():
                for item in PUBLIC_DOWNLOADS_DIR.iterdir():
                    if item.is_file():
                        file_age = now - item.stat().st_mtime
                        if file_age > max_age:
                            print(f"[API Cleanup] Removing old file: {item}")
                            try:
                                item.unlink()
                            except OSError as e:
                                print(f"[API Cleanup] Error deleting file {item}: {e}")
        except Exception as e:
            print(f"[API Cleanup] Error in background task: {e}")
        
        await asyncio.sleep(int(os.environ.get("CLEANUP_INTERVAL_SEC", 300)))  # default 5 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure public downloads directory exists
    PUBLIC_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Start cleanup task
    cleanup_task = asyncio.create_task(cleanup_old_files())
    yield
    # Shutdown cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

# Initialize FastAPI App
app = FastAPI(
    title="Telegram Music Downloader API",
    description="API for searching and downloading music from Deezer (Isolated Service)",
    version="1.0.0",
    lifespan=lifespan,
)

# Enforce Header-based API Key Authentication
async def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )

# Serve root web dashboard UI
@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = API_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("index.html not found", status_code=404)
    with open(index_file, "r", encoding="utf-8") as f:
        content = f.read()
        content = content.replace("{{SERVER_API_KEY}}", API_KEY)
        return HTMLResponse(content)

# Key hint helper endpoint for frontend to prefill the key if running locally with default credentials
@app.get("/api/key-hint")
async def get_key_hint():
    return {"default_key": API_KEY if API_KEY == "dev-key" else None}

# Mount static downloads directory
app.mount("/static", StaticFiles(directory=str(PUBLIC_DOWNLOADS_DIR)), name="static")

@app.get("/api/search")
async def search_all(q: str = Query(..., min_length=1), _=Depends(verify_api_key)):
    """Search for query across tracks, albums, and artists concurrently."""
    try:
        # Run blocking search calls in threads to avoid blocking the event loop
        tracks_task = asyncio.to_thread(deezer_search, q, TYPE_TRACK)
        albums_task = asyncio.to_thread(deezer_search, q, TYPE_ALBUM)
        artists_task = asyncio.to_thread(deezer_search, q, TYPE_ARTIST)
        
        tracks, albums, artists = await asyncio.gather(
            tracks_task, albums_task, artists_task, return_exceptions=True
        )
        
        # Check and extract results or fall back to empty list on failure
        res_tracks = tracks if not isinstance(tracks, Exception) else []
        res_albums = albums if not isinstance(albums, Exception) else []
        res_artists = artists if not isinstance(artists, Exception) else []
        
        if isinstance(tracks, Exception):
            print(f"Error searching tracks: {tracks}")
        if isinstance(albums, Exception):
            print(f"Error searching albums: {albums}")
        if isinstance(artists, Exception):
            print(f"Error searching artists: {artists}")

        return {
            "query": q,
            "tracks": res_tracks,
            "albums": res_albums,
            "artists": res_artists
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {e}",
        )

@app.get("/api/search/tracks")
async def search_tracks(q: str = Query(..., min_length=1), _=Depends(verify_api_key)):
    """Search for tracks matching the query."""
    try:
        tracks = await asyncio.to_thread(deezer_search, q, TYPE_TRACK)
        return {"query": q, "results": tracks}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Track search failed: {e}",
        )

@app.get("/api/search/albums")
async def search_albums(q: str = Query(..., min_length=1), _=Depends(verify_api_key)):
    """Search for albums matching the query."""
    try:
        albums = await asyncio.to_thread(deezer_search, q, TYPE_ALBUM)
        return {"query": q, "results": albums}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Album search failed: {e}",
        )

@app.get("/api/search/artists")
async def search_artists(q: str = Query(..., min_length=1), _=Depends(verify_api_key)):
    """Search for artists matching the query."""
    try:
        artists = await asyncio.to_thread(deezer_search, q, TYPE_ARTIST)
        return {"query": q, "results": artists}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Artist search failed: {e}",
        )

@app.get("/api/download/track/{track_id}")
async def download_track_endpoint(
    request: Request,
    track_id: str,
    quality: str = Query(None),
    _=Depends(verify_api_key)
):
    """Download a track and return a temporary downloadable web link."""
    # Validate quality argument
    if quality:
        quality = quality.lower()
        if quality not in ["flac", "mp3", "mp3_320", "mp3_128", "auto"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid quality. Allowed values: flac, mp3, mp3_320, mp3_128, auto"
            )
    else:
        quality = "auto"

    async with download_lock:
        # Override quality settings globally for this download step
        original_format = deezer_download.sound_format
        if quality != "auto":
            if quality == "flac":
                deezer_download.sound_format = "FLAC"
            elif quality in ["mp3_320", "mp3"]:
                deezer_download.sound_format = "MP3_320"
            else:
                deezer_download.sound_format = "MP3_128"
        
        try:
            print(f"[API] Downloading track {track_id} with format {deezer_download.sound_format} (requested: {quality})")
            result = await download_track(track_id, quality=quality)
            if not result or "song_path" not in result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Track {track_id} could not be downloaded or was not found."
                )
            
            # Construct friendly public filename
            artist = result.get("artist_name", "Unknown Artist")
            title = result.get("song_name", f"Track {track_id}")
            ext = result.get("file_extension", ".mp3")
            clean_name = clean_filename(f"{artist} - {title}")
            public_filename = f"{clean_name}_{track_id}{ext}"
            public_filepath = PUBLIC_DOWNLOADS_DIR / public_filename
            
            # Copy file to public server folder
            shutil.copy2(result["song_path"], public_filepath)
            
            # Cleanup original download directory
            original_dir = Path(result["download_dir"])
            if original_dir.exists():
                shutil.rmtree(str(original_dir), ignore_errors=True)
                
            # Build public URL
            base_url = str(request.base_url)
            download_url = f"{base_url.rstrip('/')}/static/{public_filename}"
            
            return {
                "status": "success",
                "track_id": track_id,
                "title": title,
                "artist": artist,
                "album": result.get("ALB_TITLE", "Unknown Album"),
                "quality_used": result.get("quality_used", deezer_download.sound_format),
                "download_url": download_url
            }
        except HTTPException:
            raise
        except Exception as e:
            print(f"[API] Error downloading track {track_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to download track: {e}"
            )
        finally:
            # Restore original default quality format
            deezer_download.sound_format = original_format

@app.get("/api/download/album/{album_id}")
async def download_album_endpoint(
    request: Request,
    album_id: str,
    quality: str = Query(None),
    _=Depends(verify_api_key)
):
    """Download an album, zip all its tracks, and return a temporary downloadable web link."""
    if quality:
        quality = quality.lower()
        if quality not in ["flac", "mp3", "mp3_320", "mp3_128", "auto"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid quality. Allowed values: flac, mp3, mp3_320, mp3_128, auto"
            )
    else:
        quality = "auto"

    async with download_lock:
        original_format = deezer_download.sound_format
        if quality != "auto":
            if quality == "flac":
                deezer_download.sound_format = "FLAC"
            elif quality in ["mp3_320", "mp3"]:
                deezer_download.sound_format = "MP3_320"
            else:
                deezer_download.sound_format = "MP3_128"
        
        try:
            print(f"[API] Downloading album {album_id} with format {deezer_download.sound_format} (requested: {quality})")
            results = await download_album(album_id, quality=quality)
            if not results:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Album {album_id} could not be downloaded or was empty."
                )
            
            # Construct friendly public ZIP filename
            first_track = results[0]
            album_title = first_track.get("ALB_TITLE", f"Album {album_id}")
            artist_name = first_track.get("ART_NAME", "Unknown Artist")
            clean_name = clean_filename(f"{artist_name} - {album_title}")
            public_filename = f"{clean_name}_{album_id}.zip"
            public_filepath = PUBLIC_DOWNLOADS_DIR / public_filename
            
            # Write zip archive
            with ZipFile(public_filepath, "w", ZIP_DEFLATED) as zipf:
                for track in results:
                    src = track["song_path"]
                    track_num = str(track.get("TRACK_NUMBER", "01")).zfill(2)
                    title = track.get("song_name", "Track")
                    ext = track.get("file_extension", ".mp3")
                    dest = clean_filename(f"{track_num} - {title}") + ext
                    
                    if Path(src).exists():
                        zipf.write(src, dest)
            
            # Cleanup original download directory
            original_dir = Path(results[0]["download_dir"])
            if original_dir.exists():
                shutil.rmtree(str(original_dir), ignore_errors=True)
                
            # Build public URL
            base_url = str(request.base_url)
            download_url = f"{base_url.rstrip('/')}/static/{public_filename}"
            
            # Collect unique qualities used for the tracks
            unique_qualities = list(set(r.get("quality_used", "UNKNOWN") for r in results))
            quality_used = unique_qualities[0] if len(unique_qualities) == 1 else ", ".join(unique_qualities)

            return {
                "status": "success",
                "album_id": album_id,
                "title": album_title,
                "artist": artist_name,
                "track_count": len(results),
                "quality_used": quality_used,
                "download_url": download_url
            }
        except HTTPException:
            raise
        except Exception as e:
            print(f"[API] Error downloading album {album_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to download album: {e}"
            )
        finally:
            deezer_download.sound_format = original_format

if __name__ == "__main__":
    import uvicorn
    api_host = os.environ.get("API_HOST", "0.0.0.0")
    api_port = int(os.environ.get("API_PORT", os.environ.get("PORT", "8000")))
    print(f"Starting separate API server on http://{api_host}:{api_port}")
    uvicorn.run(app, host=api_host, port=api_port)
