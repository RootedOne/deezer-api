import os
import asyncio
from pathlib import Path
import aioshutil

# Import local modules
from utils import TMP_DIR
from dl_utils.deezer_utils import clean_filename
from dl_utils.deezer_download import (
    init_deezer_session,
    get_song_infos_from_deezer_website,
    download_song,
    get_file_format,
)

MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 5))
DEFAULT_QUALITY = "flac" if os.environ.get("ENABLE_FLAC") == "1" else "mp3"

# Initialize Deezer session globally if token is present
deezer_token = os.environ.get("DEEZER_TOKEN")
if not deezer_token:
    print("WARNING: DEEZER_TOKEN environment variable not set. Deezer downloads will fail.")
else:
    init_deezer_session("", DEFAULT_QUALITY)

async def download_track(track_id, retries=MAX_RETRIES):
    """Downloads a single track from Deezer using local functions, without Telegram bot dependencies."""
    tmp_track_base_dir = None

    for attempt in range(retries):
        try:
            # Fetch track metadata from Deezer website (may include download details)
            track_infos = get_song_infos_from_deezer_website("track", track_id)
            if not track_infos:
                print(f"Attempt {attempt + 1}: Could not get track info for {track_id}")
                if attempt < retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                else:
                    raise ValueError(
                        f"Failed to get track info for {track_id} after {retries} attempts."
                    )

            # Make sure track_infos is a dictionary, not a list
            if isinstance(track_infos, list):
                if len(track_infos) > 0:
                    track_infos = track_infos[0]  # Take the first item if it's a list
                else:
                    raise ValueError(
                        f"Empty track info list received for track {track_id}"
                    )

            file_extension, deezer_format = get_file_format(track_infos)

            # Create a temporary directory for this track
            tmp_track_base_dir = Path(TMP_DIR) / "deezer" / "track" / str(track_id)
            tmp_track_base_dir.mkdir(parents=True, exist_ok=True)

            # Determine the expected final file path within our base dir
            song_path = tmp_track_base_dir / f"{track_id}{file_extension}"

            # Perform the actual download
            download_song(
                track_infos, deezer_format, str(song_path)
            )

            # Check if download was successful
            if not song_path.exists() or song_path.stat().st_size == 0:
                if song_path.exists():
                    try:
                        song_path.unlink()
                    except OSError:
                        pass
                raise IOError(f"Downloaded file {song_path} is missing or empty.")

            # Add download-specific details to the track_infos dictionary
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
            
            if isinstance(track_infos, dict) and "TRACK_NUMBER" in track_infos:
                track_info_dict["TRACK_NUMBER"] = track_infos["TRACK_NUMBER"]

            print(f"Successfully downloaded track {track_id} to {song_path}")
            return track_info_dict

        except Exception as e:
            print(
                f"Error downloading track {track_id} on attempt {attempt + 1}/{retries}: {e}"
            )
            if attempt < retries - 1:
                sleep_time = 1 * (attempt + 1)
                print(f"Retrying in {sleep_time} seconds...")
                await asyncio.sleep(sleep_time)
            else:
                print(f"Failed to download track {track_id} after {retries} attempts.")
                if tmp_track_base_dir and tmp_track_base_dir.exists():
                    await aioshutil.rmtree(tmp_track_base_dir, ignore_errors=True)
                raise

    if tmp_track_base_dir and tmp_track_base_dir.exists():
        await aioshutil.rmtree(tmp_track_base_dir, ignore_errors=True)
    return None

async def download_album(album_id, retries=MAX_RETRIES):
    """Downloads all tracks from a Deezer album using local functions, without Telegram bot dependencies."""
    album_info_attempt = 0
    album_tracks_infos = None
    tmp_download_dir = None

    while album_info_attempt < retries:
        try:
            album_tracks_infos = get_song_infos_from_deezer_website("album", album_id)
            if not album_tracks_infos:
                raise ValueError(
                    f"Could not get album info for {album_id} (empty list received)"
                )

            # Create a temporary directory for this album download ONCE
            tmp_download_dir = Path(TMP_DIR) / "deezer" / "album" / str(album_id)
            tmp_download_dir.mkdir(parents=True, exist_ok=True)
            print(
                f"Album metadata fetched successfully. Download dir: {tmp_download_dir}"
            )
            break

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
                print(
                    f"Failed to get album info for {album_id} after {retries} attempts."
                )
                if tmp_download_dir and tmp_download_dir.exists():
                    await aioshutil.rmtree(tmp_download_dir, ignore_errors=True)
                raise

    if not album_tracks_infos or not tmp_download_dir:
        print(f"Failed to initialize album download for {album_id}.")
        return None

    downloaded_tracks_details = []
    tasks = []

    for i, track_infos in enumerate(album_tracks_infos):
        track_sng_id = track_infos.get("SNG_ID", f"album_{album_id}_track_{i}")
        file_extension, deezer_format = get_file_format(track_infos)
        song_path = tmp_download_dir / f"{track_sng_id}{file_extension}"

        async def download_single_with_retry(ti, fe, df, sp, track_retries=MAX_RETRIES):
            track_id = ti.get("SNG_ID", "N/A")
            for attempt in range(track_retries):
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
                    if "TRACK_NUMBER" in ti:
                        ti_copy["TRACK_NUMBER"] = ti["TRACK_NUMBER"]

                    print(
                        f"Successfully downloaded track {track_id} to {sp} (attempt {attempt + 1})"
                    )
                    return ti_copy

                except Exception as track_e:
                    print(
                        f"Error downloading track {track_id} (attempt {attempt + 1}/{track_retries}): {track_e}"
                    )
                    if sp.exists():
                        try:
                            sp.unlink()
                        except OSError:
                            pass

                    if attempt < track_retries - 1:
                        sleep_time = 1 * (attempt + 1)
                        print(f"Retrying track {track_id} in {sleep_time} seconds...")
                        await asyncio.sleep(sleep_time)
                    else:
                        print(
                            f"Failed to download track {track_id} after {track_retries} attempts."
                        )
                        return None

            return None

        tasks.append(
            download_single_with_retry(
                track_infos, file_extension, deezer_format, song_path
            )
        )

    results = await asyncio.gather(*tasks)
    downloaded_tracks_details = [res for res in results if res is not None]

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
