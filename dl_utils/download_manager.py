import asyncio
import uuid
import shutil
import os
import aioshutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from utils import TMP_DIR
from dl_utils.deezer_utils import clean_filename
from dl_utils.deezer_download import (
    DOWNLOAD_CALLBACKS,
    get_song_infos_from_deezer_website,
)
import download

# Path to serve completed files
PUBLIC_DOWNLOADS_DIR = Path(__file__).resolve().parent.parent / "tmp" / "public_downloads"
PUBLIC_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

class DownloadItem:
    def __init__(self, download_id, item_id, item_type, title, artist, cover_url, quality):
        self.id = download_id
        self.item_id = item_id
        self.type = item_type  # 'track' or 'album'
        self.title = title
        self.artist = artist
        self.cover_url = cover_url
        self.quality = quality
        self.status = "queued"  # queued, downloading, paused, completed, failed, cancelled
        self.progress = 0
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.download_url = None
        self.error = None
        self.child_ids = []  # Child track download IDs (if album)
        self.parent_id = None  # Parent album download ID (if child track)
        
        # Performance/ETA stats
        self.start_time = None
        self.speed = 0
        self.eta = None

    def to_dict(self):
        return {
            "id": self.id,
            "item_id": self.item_id,
            "type": self.type,
            "title": self.title,
            "artist": self.artist,
            "cover_url": self.cover_url,
            "quality": self.quality,
            "status": self.status,
            "progress": self.progress,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "download_url": self.download_url,
            "error": self.error,
            "child_ids": self.child_ids,
            "parent_id": self.parent_id,
            "speed": self.speed,
            "eta": self.eta
        }

class DownloadManager:
    def __init__(self):
        self.items = {}  # download_id -> DownloadItem
        self._lock = asyncio.Lock()
        
        # Register the callbacks in deezer_download
        DOWNLOAD_CALLBACKS["is_paused"] = self.is_paused
        DOWNLOAD_CALLBACKS["is_cancelled"] = self.is_cancelled
        DOWNLOAD_CALLBACKS["update_progress"] = self.update_progress

    def is_paused(self, download_id: str) -> bool:
        item = self.items.get(download_id)
        if not item:
            return False
        # If the child track itself or its parent is paused, then it is paused
        if item.status == "paused":
            return True
        if item.parent_id:
            parent = self.items.get(item.parent_id)
            if parent and parent.status == "paused":
                return True
        return False

    def is_cancelled(self, download_id: str) -> bool:
        item = self.items.get(download_id)
        if not item:
            return False
        if item.status == "cancelled":
            return True
        if item.parent_id:
            parent = self.items.get(item.parent_id)
            if parent and parent.status == "cancelled":
                return True
        return False

    def update_progress(self, download_id: str, progress: int, downloaded: int, total: int):
        item = self.items.get(download_id)
        if not item:
            return
        
        # Only update if the item is currently downloading
        if item.status not in ["downloading", "queued"]:
            return
        
        item.status = "downloading"
        item.progress = progress
        item.downloaded_bytes = downloaded
        item.total_bytes = total
        
        # Calculate speed and ETA
        import time
        if not item.start_time:
            item.start_time = time.time()
        
        elapsed = time.time() - item.start_time
        if elapsed > 0.1:
            item.speed = int(downloaded / elapsed)
            remaining_bytes = total - downloaded
            if item.speed > 0:
                item.eta = int(remaining_bytes / item.speed)
            else:
                item.eta = None
        
        # If this is a child track of an album, recalculate parent album's progress
        if item.parent_id:
            parent = self.items.get(item.parent_id)
            if parent and parent.child_ids:
                total_progress = 0
                total_downloaded = 0
                total_bytes = 0
                total_speed = 0
                completed_count = 0
                
                for cid in parent.child_ids:
                    citem = self.items.get(cid)
                    if citem:
                        total_progress += citem.progress
                        total_downloaded += citem.downloaded_bytes
                        total_bytes += citem.total_bytes
                        total_speed += getattr(citem, "speed", 0)
                        if citem.status == "completed":
                            completed_count += 1
                
                parent.progress = int(total_progress / len(parent.child_ids))
                parent.downloaded_bytes = total_downloaded
                parent.total_bytes = total_bytes
                parent.speed = total_speed
                
                if parent.speed > 0 and parent.total_bytes > parent.downloaded_bytes:
                    parent.eta = int((parent.total_bytes - parent.downloaded_bytes) / parent.speed)
                else:
                    parent.eta = None
                
                # Set dynamic progress/completed count status for album
                if parent.status in ["downloading", "queued"]:
                    parent.status = "downloading"

    def queue_track(self, track_id: str, quality: str, title: str, artist: str, cover_url: str) -> str:
        download_id = f"track_{track_id}_{uuid.uuid4().hex[:6]}"
        item = DownloadItem(download_id, track_id, "track", title, artist, cover_url, quality)
        self.items[download_id] = item
        
        # Kick off background task
        asyncio.create_task(self._download_track_task(download_id))
        return download_id

    def queue_album(self, album_id: str, quality: str, title: str, artist: str, cover_url: str) -> str:
        download_id = f"album_{album_id}_{uuid.uuid4().hex[:6]}"
        item = DownloadItem(download_id, album_id, "album", title, artist, cover_url, quality)
        self.items[download_id] = item
        
        # Kick off background task
        asyncio.create_task(self._download_album_task(download_id))
        return download_id

    async def _download_track_task(self, download_id: str):
        item = self.items.get(download_id)
        if not item:
            return
        
        item.status = "downloading"
        try:
            result = await download.download_track(item.item_id, quality=item.quality, download_id=download_id)
            if not result or "song_path" not in result:
                raise ValueError("Download succeeded but no output path was returned.")
            
            # Construct friendly public filename
            artist = result.get("artist_name", item.artist)
            title = result.get("song_name", item.title)
            ext = result.get("file_extension", ".mp3")
            clean_name = clean_filename(f"{artist} - {title}")
            public_filename = f"{clean_name}_{item.item_id}{ext}"
            public_filepath = PUBLIC_DOWNLOADS_DIR / public_filename
            
            # Copy to static downloads folder
            shutil.copy2(result["song_path"], public_filepath)
            
            # Clean up original download folder
            original_dir = Path(result["download_dir"])
            if original_dir.exists():
                shutil.rmtree(str(original_dir), ignore_errors=True)
            
            # Update item status
            item.status = "completed"
            item.progress = 100
            item.download_url = f"/static/{public_filename}"
            print(f"[DownloadManager] Successfully completed track: {download_id}")
            
        except Exception as e:
            if self.is_cancelled(download_id):
                item.status = "cancelled"
                print(f"[DownloadManager] Track cancelled: {download_id}")
            else:
                item.status = "failed"
                item.error = str(e)
                print(f"[DownloadManager] Track failed: {download_id}: {e}")

    async def _download_album_task(self, download_id: str):
        item = self.items.get(download_id)
        if not item:
            return
        
        item.status = "downloading"
        try:
            # 1. Fetch metadata first to know what tracks are in the album
            album_tracks_infos = await asyncio.to_thread(get_song_infos_from_deezer_website, "album", item.item_id)
            if not album_tracks_infos:
                raise ValueError("Failed to retrieve track infos for the album from Deezer website.")
            
            if not isinstance(album_tracks_infos, list):
                album_tracks_infos = [album_tracks_infos]
            
            # 2. Register child track items
            child_ids = []
            for idx, track_info in enumerate(album_tracks_infos):
                track_id = str(track_info.get("SNG_ID", f"child_{idx}"))
                title = track_info.get("SNG_TITLE", f"Track {idx + 1}")
                artist = track_info.get("ART_NAME", item.artist)
                child_dl_id = f"child_track_{track_id}_{uuid.uuid4().hex[:6]}"
                
                child_item = DownloadItem(
                    child_dl_id, track_id, "track", title, artist, item.cover_url, item.quality
                )
                child_item.parent_id = download_id
                self.items[child_dl_id] = child_item
                child_ids.append(child_dl_id)
            
            item.child_ids = child_ids
            
            # Update child items to 'downloading'
            for cid in child_ids:
                self.items[cid].status = "downloading"
            
            # 3. Call the album downloader passing child download IDs
            results = await download.download_album(
                item.item_id, quality=item.quality, parent_download_id=download_id, child_ids=child_ids
            )
            
            # Check for cancellation or failure
            if self.is_cancelled(download_id):
                raise asyncio.CancelledError()
            
            if not results:
                raise ValueError("Album downloaded, but no tracks were successfully processed.")
            
            # 4. Mark all children that successfully downloaded as completed
            for track_result in results:
                # Find corresponding child item
                track_id = str(track_result.get("SNG_ID"))
                for cid in child_ids:
                    citem = self.items[cid]
                    if citem.item_id == track_id:
                        citem.status = "completed"
                        citem.progress = 100
            
            # Ensure children are updated correctly
            for cid in child_ids:
                if self.items[cid].status == "downloading":
                    self.items[cid].status = "failed"
                    self.items[cid].error = "Unknown track download error"
            
            # 5. Create the ZIP archive
            first_track = results[0]
            album_title = first_track.get("ALB_TITLE", item.title)
            artist_name = first_track.get("ART_NAME", item.artist)
            clean_name = clean_filename(f"{artist_name} - {album_title}")
            public_filename = f"{clean_name}_{item.item_id}.zip"
            public_filepath = PUBLIC_DOWNLOADS_DIR / public_filename
            
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
                
            # Update parent item status
            item.status = "completed"
            item.progress = 100
            item.download_url = f"/static/{public_filename}"
            print(f"[DownloadManager] Successfully completed album: {download_id}")
            
        except asyncio.CancelledError:
            item.status = "cancelled"
            for cid in item.child_ids:
                self.items[cid].status = "cancelled"
            print(f"[DownloadManager] Album cancelled: {download_id}")
            
        except Exception as e:
            if self.is_cancelled(download_id):
                item.status = "cancelled"
                for cid in item.child_ids:
                    self.items[cid].status = "cancelled"
                print(f"[DownloadManager] Album cancelled: {download_id}")
            else:
                item.status = "failed"
                item.error = str(e)
                # Fail all active child tracks too
                for cid in item.child_ids:
                    citem = self.items[cid]
                    if citem.status in ["downloading", "queued"]:
                        citem.status = "failed"
                        citem.error = str(e)
                print(f"[DownloadManager] Album failed: {download_id}: {e}")

    def pause_download(self, download_id: str) -> bool:
        item = self.items.get(download_id)
        if not item:
            return False
        if item.status in ["queued", "downloading"]:
            item.status = "paused"
            # Pause all child tracks if this is an album
            if item.type == "album":
                for cid in item.child_ids:
                    citem = self.items.get(cid)
                    if citem and citem.status in ["queued", "downloading"]:
                        citem.status = "paused"
            return True
        return False

    def resume_download(self, download_id: str) -> bool:
        item = self.items.get(download_id)
        if not item:
            return False
        if item.status == "paused":
            item.status = "downloading"
            # Resume all child tracks if this is an album
            if item.type == "album":
                for cid in item.child_ids:
                    citem = self.items.get(cid)
                    if citem and citem.status == "paused":
                        citem.status = "downloading"
            return True
        return False

    def cancel_download(self, download_id: str) -> bool:
        item = self.items.get(download_id)
        if not item:
            return False
        if item.status in ["queued", "downloading", "paused"]:
            item.status = "cancelled"
            # Cancel all child tracks if this is an album
            if item.type == "album":
                for cid in item.child_ids:
                    citem = self.items.get(cid)
                    if citem and citem.status in ["queued", "downloading", "paused"]:
                        citem.status = "cancelled"
            return True
        return False

    def delete_download(self, download_id: str) -> bool:
        item = self.items.get(download_id)
        if not item:
            return False
        # Cancel if active
        self.cancel_download(download_id)
        # Remove child items if it's an album
        if item.type == "album":
            for cid in item.child_ids:
                if cid in self.items:
                    del self.items[cid]
        if download_id in self.items:
            del self.items[download_id]
            return True
        return False

    def clear_downloads(self):
        # Remove all completed, failed or cancelled items
        to_remove = [k for k, v in self.items.items() if v.status in ["completed", "failed", "cancelled"] and v.parent_id is None]
        for k in to_remove:
            # Also remove child track items
            item = self.items[k]
            for cid in item.child_ids:
                if cid in self.items:
                    del self.items[cid]
            del self.items[k]

# Global shared instance of the download manager
download_manager = DownloadManager()
