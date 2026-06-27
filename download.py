import os
import asyncio
import shutil
from pathlib import Path
import aioshutil

# Import local modules
from utils import TMP_DIR
from dl_utils.deezer_utils import clean_filename
import dl_utils.deezer_download as deezer_download
from dl_utils.deezer_download import (
    init_deezer_session,
    get_song_infos_from_deezer_website,
    download_song,
    get_file_format,
)

MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 5))
DEFAULT_QUALITY = "flac" if os.environ.get("ENABLE_FLAC") == "1" else "mp3"

# Scan for all fallback tokens at startup
DEEZER_TOKENS = []
i = 1
while True:
    token = os.environ.get(f"DEEZER_TOKEN_{i}")
    if not token:
        if i == 1:
            default_token = os.environ.get("DEEZER_TOKEN")
            if default_token:
                DEEZER_TOKENS.append(default_token)
        break
    DEEZER_TOKENS.append(token)
    i += 1

CURRENT_TOKEN_INDEX = 0

def rotate_account():
    global CURRENT_TOKEN_INDEX
    if not DEEZER_TOKENS:
        return
    old_index = CURRENT_TOKEN_INDEX
    CURRENT_TOKEN_INDEX = (CURRENT_TOKEN_INDEX + 1) % len(DEEZER_TOKENS)
    print(f"[Fallback Auth] Rotating active Deezer account from {old_index + 1} to {CURRENT_TOKEN_INDEX + 1}")
    
    # Initialize the session for the newly rotated account index
    try:
        init_deezer_session("", DEFAULT_QUALITY, DEEZER_TOKENS[CURRENT_TOKEN_INDEX])
        print(f"[Fallback Auth] Deezer session successfully rotated and initialized for account {CURRENT_TOKEN_INDEX + 1}")
    except Exception as e:
        print(f"[Fallback Auth] ERROR: Failed to initialize session for rotated account index {CURRENT_TOKEN_INDEX + 1}: {e}")

def try_initialize_any_session():
    global CURRENT_TOKEN_INDEX
    if not DEEZER_TOKENS:
        print("WARNING: No Deezer tokens configured. Deezer downloads will fail.")
        return False
        
    start_index = CURRENT_TOKEN_INDEX
    while True:
        token = DEEZER_TOKENS[CURRENT_TOKEN_INDEX]
        try:
            print(f"[Fallback Auth] Initializing Deezer session with account {CURRENT_TOKEN_INDEX + 1}/{len(DEEZER_TOKENS)}")
            init_deezer_session("", DEFAULT_QUALITY, token)
            print(f"[Fallback Auth] Deezer session initialized successfully with account {CURRENT_TOKEN_INDEX + 1}")
            return True
        except Exception as e:
            print(f"[Fallback Auth] ERROR: Failed to initialize Deezer session with account {CURRENT_TOKEN_INDEX + 1}: {e}")
            CURRENT_TOKEN_INDEX = (CURRENT_TOKEN_INDEX + 1) % len(DEEZER_TOKENS)
            if CURRENT_TOKEN_INDEX == start_index:
                print("[Fallback Auth] ERROR: All configured Deezer tokens failed to initialize session.")
                return False

# Initialize the starting active session
try_initialize_any_session()

async def execute_with_account_fallback(func, *args, **kwargs):
    """Executes a download function with fallback account rotation on failure."""
    if not DEEZER_TOKENS:
        return await func(*args, **kwargs)
        
    start_index = CURRENT_TOKEN_INDEX
    attempts = 0
    max_attempts = len(DEEZER_TOKENS)
    
    while attempts < max_attempts:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            attempts += 1
            print(f"[Fallback Auth] Execution failed using account {CURRENT_TOKEN_INDEX + 1}: {e}")
            if attempts < max_attempts:
                rotate_account()
            else:
                print("[Fallback Auth] All fallback accounts have been tried and failed.")
                raise e

async def download_track(track_id, quality=None, retries=MAX_RETRIES):
    """Downloads a single track from Deezer with fallback quality support if quality='auto' or None, wrapped in fallback accounts."""
    async def _download_track_impl():
        if quality is None or quality.lower() == "auto":
            formats_to_try = ["FLAC", "MP3_320", "MP3_128"]
        else:
            q_val = quality.lower()
            if q_val == "flac":
                formats_to_try = ["FLAC"]
            elif q_val in ["mp3_320", "mp3"]:
                formats_to_try = ["MP3_320"]
            else:
                formats_to_try = ["MP3_128"]

        tmp_track_base_dir = None
        last_exception = None

        track_infos = None
        for attempt in range(retries):
            try:
                track_infos = get_song_infos_from_deezer_website("track", track_id)
                if track_infos:
                    break
            except Exception as e:
                print(f"Attempt {attempt + 1}: Error getting track info for {track_id}: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    raise ValueError(
                        f"Failed to get track info for {track_id} after {retries} attempts."
                    ) from e

        if not track_infos:
            raise ValueError(f"Failed to get track info for {track_id}.")

        if isinstance(track_infos, list):
            if len(track_infos) > 0:
                track_infos = track_infos[0]
            else:
                raise ValueError(
                    f"Empty track info list received for track {track_id}"
                )

        tried_formats = set()
        for format_name in formats_to_try:
            # Set the global format for get_file_format to read (synchronous operation)
            deezer_download.sound_format = format_name

            file_extension, deezer_format = get_file_format(track_infos)

            if deezer_format in tried_formats:
                continue
            tried_formats.add(deezer_format)

            print(f"Attempting download of track {track_id} in format {deezer_format} (requested: {format_name})")

            tmp_track_base_dir = Path(TMP_DIR) / "deezer" / "track" / f"{track_id}_{deezer_format}"
            tmp_track_base_dir.mkdir(parents=True, exist_ok=True)
            song_path = tmp_track_base_dir / f"{track_id}{file_extension}"

            for attempt in range(retries):
                try:
                    download_song(
                        track_infos, deezer_format, str(song_path)
                    )

                    if not song_path.exists() or song_path.stat().st_size == 0:
                        if song_path.exists():
                            try:
                                song_path.unlink()
                            except OSError:
                                pass
                        raise IOError(f"Downloaded file {song_path} is missing or empty.")

                    track_info_dict = {}
                    if isinstance(track_infos, dict):
                        track_info_dict = track_infos.copy()

                    track_info_dict["song_path"] = str(song_path)
                    track_info_dict["song_name"] = (
                        track_infos.get("SNG_TITLE", f"Track {track_id}")
                        if isinstance(track_infos, dict)
                        else f"Track {track_id}"
                    )
                    track_info_dict["artist_name"] = (
                        track_infos.get("ART_NAME", "Unknown Artist")
                        if isinstance(track_infos, dict)
                        else "Unknown Artist"
                    )
                    track_info_dict["file_extension"] = file_extension
                    track_info_dict["download_dir"] = str(tmp_track_base_dir)
                    track_info_dict["quality_used"] = deezer_format
                    
                    if isinstance(track_infos, dict) and "TRACK_NUMBER" in track_infos:
                        track_info_dict["TRACK_NUMBER"] = track_infos["TRACK_NUMBER"]

                    print(f"Successfully downloaded track {track_id} to {song_path}")
                    return track_info_dict

                except Exception as e:
                    print(
                        f"Error downloading track {track_id} in format {deezer_format} on attempt {attempt + 1}/{retries}: {e}"
                    )
                    last_exception = e
                    if song_path.exists():
                        try:
                            song_path.unlink()
                        except OSError:
                            pass
                    if attempt < retries - 1:
                        sleep_time = 1 * (attempt + 1)
                        print(f"Retrying in {sleep_time} seconds...")
                        await asyncio.sleep(sleep_time)

            # Clean up directory if the format failed after all attempts
            if tmp_track_base_dir and tmp_track_base_dir.exists():
                shutil.rmtree(str(tmp_track_base_dir), ignore_errors=True)

        raise last_exception or ValueError(f"Failed to download track {track_id} after trying formats: {formats_to_try}")

    return await execute_with_account_fallback(_download_track_impl)

async def download_album(album_id, quality=None, retries=MAX_RETRIES):
    """Downloads all tracks from a Deezer album using local functions, without Telegram bot dependencies."""
    album_info_attempt = 0
    album_tracks_infos = None
    tmp_download_dir = None

    async def get_metadata_with_fallback():
        nonlocal album_info_attempt, album_tracks_infos, tmp_download_dir
        while album_info_attempt < retries:
            try:
                infos = get_song_infos_from_deezer_website("album", album_id)
                if not infos:
                    raise ValueError(
                        f"Could not get album info for {album_id} (empty list received)"
                    )
                # Create a temporary directory for this album download ONCE
                tmp_download_dir = Path(TMP_DIR) / "deezer" / "album" / str(album_id)
                tmp_download_dir.mkdir(parents=True, exist_ok=True)
                print(
                    f"Album metadata fetched successfully. Download dir: {tmp_download_dir}"
                )
                return infos
            except Exception as e:
                album_info_attempt += 1
                print(
                    f"Attempt {album_info_attempt}/{retries}: Error fetching album info for {album_id}: {e}"
                )
                if album_info_attempt < retries:
                    sleep_time = 1 * album_info_attempt
                    print(f"Retrying album info fetch in {sleep_time} seconds...")
                    await asyncio.sleep(sleep_time)
                else:
                    if tmp_download_dir and tmp_download_dir.exists():
                        await aioshutil.rmtree(tmp_download_dir, ignore_errors=True)
                    raise

    album_tracks_infos = await execute_with_account_fallback(get_metadata_with_fallback)

    if not album_tracks_infos or not tmp_download_dir:
        print(f"Failed to initialize album download for {album_id}.")
        return None

    # Define quality formats to try
    if quality is None or quality.lower() == "auto":
        formats_to_try = ["FLAC", "MP3_320", "MP3_128"]
    else:
        q_val = quality.lower()
        if q_val == "flac":
            formats_to_try = ["FLAC"]
        elif q_val in ["mp3_320", "mp3"]:
            formats_to_try = ["MP3_320"]
        else:
            formats_to_try = ["MP3_128"]

    downloaded_tracks_details = []
    tasks = []

    for i, track_infos in enumerate(album_tracks_infos):
        track_id = track_infos.get("SNG_ID", f"album_{album_id}_track_{i}")

        async def download_single_track_with_fallback(ti, track_id):
            async def _download_track_task():
                last_exception = None
                tried_formats = set()

                for format_name in formats_to_try:
                    # Set the global format for get_file_format to read (synchronous operation)
                    deezer_download.sound_format = format_name

                    # Determine format based on metadata
                    fe, df = get_file_format(ti)

                    if df in tried_formats:
                        continue
                    tried_formats.add(df)

                    sp = tmp_download_dir / f"{track_id}{fe}"

                    for attempt in range(retries):
                        try:
                            download_song(ti, df, str(sp))

                            if not sp.exists() or sp.stat().st_size == 0:
                                if sp.exists():
                                    try:
                                        sp.unlink()
                                    except OSError:
                                        pass
                                raise IOError(f"Downloaded file {sp} is missing or empty.")

                            ti_copy = ti.copy()
                            ti_copy["song_path"] = str(sp)
                            ti_copy["song_name"] = ti_copy.get("SNG_TITLE", f"Track {track_id}")
                            ti_copy["artist_name"] = ti_copy.get("ART_NAME", "Unknown Artist")
                            ti_copy["file_extension"] = fe
                            ti_copy["quality_used"] = df
                            if "TRACK_NUMBER" in ti:
                                ti_copy["TRACK_NUMBER"] = ti["TRACK_NUMBER"]

                            print(
                                f"Successfully downloaded track {track_id} in format {df} to {sp} (attempt {attempt + 1})"
                            )
                            return ti_copy

                        except Exception as track_e:
                            print(
                                f"Error downloading track {track_id} in format {df} (attempt {attempt + 1}/{retries}): {track_e}"
                            )
                            if sp.exists():
                                try:
                                    sp.unlink()
                                except OSError:
                                    pass
                            last_exception = track_e
                            if attempt < retries - 1:
                                await asyncio.sleep(1 * (attempt + 1))

                raise last_exception or Exception(f"Track {track_id} failed in all formats.")

            return await execute_with_account_fallback(_download_track_task)

        tasks.append(download_single_track_with_fallback(track_infos, track_id))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    downloaded_tracks_details = [res for res in results if res is not None and not isinstance(res, Exception)]

    if not downloaded_tracks_details:
        print(f"Failed to download any tracks for album {album_id}.")
        if tmp_download_dir and tmp_download_dir.exists():
            await aioshutil.rmtree(tmp_download_dir, ignore_errors=True)
        raise Exception(
            f"Failed to download any tracks for album {album_id} after retries."
        )

    for track_detail in downloaded_tracks_details:
        track_detail["download_dir"] = str(tmp_download_dir)

    print(
        f"Successfully downloaded {len(downloaded_tracks_details)} out of {len(album_tracks_infos)} tracks for album {album_id} to {tmp_download_dir}"
    )
    return downloaded_tracks_details
