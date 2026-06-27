import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Set up dummy environment variables before importing
os.environ.setdefault("DEEZER_TOKEN", "dummy-arl-token")
os.environ.setdefault("API_KEY", "test-api-key")

# Add local directory to sys.path so we can import main
API_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(API_DIR))

from fastapi.testclient import TestClient

# Mock requests.session inside deezer_download to prevent import/login issues
with patch("requests.session") as mock_session:
    import main
    from main import app

client = TestClient(app)

def test_unauthorized_access():
    """Verify that requests without a valid API key header are rejected."""
    # No header
    response = client.get("/api/search?q=test")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API Key"

    # Wrong header
    response = client.get("/api/search?q=test", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401

def test_search_endpoint():
    """Verify that search returns structured results from deezer_search."""
    mock_results = [{"id": "123", "title": "Test Song", "artist": "Test Artist"}]
    
    with patch("main.deezer_search", return_value=mock_results) as mock_search:
        response = client.get("/api/search?q=pink+floyd", headers={"X-API-Key": "test-api-key"})
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "pink floyd"
        assert len(data["tracks"]) == 1
        assert len(data["albums"]) == 1
        assert len(data["artists"]) == 1
        mock_search.assert_any_call("pink floyd", "track")
        mock_search.assert_any_call("pink floyd", "album")
        mock_search.assert_any_call("pink floyd", "artist")

def test_search_tracks_endpoint():
    """Verify that /api/search/tracks works correctly."""
    mock_results = [{"id": "123", "title": "Test Song", "artist": "Test Artist"}]
    
    with patch("main.deezer_search", return_value=mock_results) as mock_search:
        response = client.get("/api/search/tracks?q=pink+floyd", headers={"X-API-Key": "test-api-key"})
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "pink floyd"
        assert len(data["results"]) == 1
        mock_search.assert_called_once_with("pink floyd", "track")

def test_download_track_endpoint():
    """Verify that downloading a track creates a local copy and returns a static file link."""
    mock_track_info = {
        "song_path": "/tmp/dummy_song.mp3",
        "download_dir": "/tmp/dummy_download_dir",
        "song_name": "Comfortably Numb",
        "artist_name": "Pink Floyd",
        "file_extension": ".mp3",
        "ALB_TITLE": "The Wall"
    }

    # Prepare temp files
    os.makedirs("/tmp/dummy_download_dir", exist_ok=True)
    with open("/tmp/dummy_song.mp3", "w") as f:
        f.write("mock audio content")

    # Mock download_track and shutil.copy2
    with patch("main.download_track", return_value=mock_track_info) as mock_download, \
         patch("shutil.copy2") as mock_copy, \
         patch("shutil.rmtree") as mock_rmtree:
         
        response = client.get("/api/download/track/123?quality=mp3", headers={"X-API-Key": "test-api-key"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "Comfortably" in data["download_url"]
        assert data["track_id"] == "123"
        assert data["quality_used"] == "MP3_320"
        
        mock_download.assert_called_once_with("123", quality="mp3")
        mock_copy.assert_called_once()
        mock_rmtree.assert_called_once_with(str(Path("/tmp/dummy_download_dir")), ignore_errors=True)

    # Clean up temp files
    try:
        os.remove("/tmp/dummy_song.mp3")
        os.rmdir("/tmp/dummy_download_dir")
    except OSError:
        pass

def test_download_album_endpoint():
    """Verify that downloading an album zips files and returns a ZIP link."""
    mock_album_results = [
        {
            "song_path": "/tmp/dummy_song1.mp3",
            "download_dir": "/tmp/dummy_album_dir",
            "song_name": "Time",
            "artist_name": "Pink Floyd",
            "file_extension": ".mp3",
            "ALB_TITLE": "Dark Side of the Moon",
            "TRACK_NUMBER": "01",
            "quality_used": "FLAC"
        }
    ]

    os.makedirs("/tmp/dummy_album_dir", exist_ok=True)
    with open("/tmp/dummy_song1.mp3", "w") as f:
        f.write("mock audio 1")

    with patch("main.download_album", return_value=mock_album_results) as mock_download, \
         patch("main.ZipFile") as mock_zip, \
         patch("shutil.rmtree") as mock_rmtree:
         
        response = client.get("/api/download/album/456?quality=flac", headers={"X-API-Key": "test-api-key"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["album_id"] == "456"
        assert data["track_count"] == 1
        assert data["quality_used"] == "FLAC"
        
        mock_download.assert_called_once_with("456", quality="flac")
        mock_zip.assert_called_once()
        mock_rmtree.assert_called_once_with(str(Path("/tmp/dummy_album_dir")), ignore_errors=True)

    try:
        os.remove("/tmp/dummy_song1.mp3")
        os.rmdir("/tmp/dummy_album_dir")
    except OSError:
        pass

def test_download_track_auto_fallback():
    """Verify that downloading a track without quality parameter defaults to auto fallback."""
    mock_track_info = {
        "song_path": "/tmp/dummy_song.mp3",
        "download_dir": "/tmp/dummy_download_dir",
        "song_name": "Comfortably Numb",
        "artist_name": "Pink Floyd",
        "file_extension": ".mp3",
        "ALB_TITLE": "The Wall",
        "quality_used": "MP3_320"
    }

    os.makedirs("/tmp/dummy_download_dir", exist_ok=True)
    with open("/tmp/dummy_song.mp3", "w") as f:
        f.write("mock audio content")

    with patch("main.download_track", return_value=mock_track_info) as mock_download, \
         patch("shutil.copy2") as mock_copy, \
         patch("shutil.rmtree") as mock_rmtree:
         
        response = client.get("/api/download/track/123", headers={"X-API-Key": "test-api-key"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["quality_used"] == "MP3_320"
        
        mock_download.assert_called_once_with("123", quality="auto")
        mock_copy.assert_called_once()
        mock_rmtree.assert_called_once_with("/tmp/dummy_download_dir", ignore_errors=True)

    try:
        os.remove("/tmp/dummy_song.mp3")
        os.rmdir("/tmp/dummy_download_dir")
    except OSError:
        pass

def test_download_album_auto_fallback():
    """Verify that downloading an album without quality parameter defaults to auto fallback."""
    mock_album_results = [
        {
            "song_path": "/tmp/dummy_song1.mp3",
            "download_dir": "/tmp/dummy_album_dir",
            "song_name": "Time",
            "artist_name": "Pink Floyd",
            "file_extension": ".mp3",
            "ALB_TITLE": "Dark Side of the Moon",
            "TRACK_NUMBER": "01",
            "quality_used": "FLAC"
        }
    ]

    os.makedirs("/tmp/dummy_album_dir", exist_ok=True)
    with open("/tmp/dummy_song1.mp3", "w") as f:
        f.write("mock audio 1")

    with patch("main.download_album", return_value=mock_album_results) as mock_download, \
         patch("main.ZipFile") as mock_zip, \
         patch("shutil.rmtree") as mock_rmtree:
         
        response = client.get("/api/download/album/456", headers={"X-API-Key": "test-api-key"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["quality_used"] == "FLAC"
        
        mock_download.assert_called_once_with("456", quality="auto")
        mock_zip.assert_called_once()
        mock_rmtree.assert_called_once_with("/tmp/dummy_album_dir", ignore_errors=True)

def test_download_track_fallback_mechanism():
    """Verify that download_track correctly falls back to lower quality when highest fails."""
    mock_infos = {
        "SNG_ID": "123",
        "SNG_TITLE": "Test Title",
        "ART_NAME": "Test Artist",
        "TRACK_NUMBER": "1"
    }
    
    with patch("download.get_song_infos_from_deezer_website", return_value=mock_infos), \
         patch("download.get_file_format") as mock_get_file_format, \
         patch("download.download_song") as mock_download_song:
         
        mock_get_file_format.side_effect = [
            (".flac", "FLAC"),
            (".mp3", "MP3_320"),
            (".mp3", "MP3_128")
        ]
        
        def mock_dl_song(ti, df, sp):
            if df == "FLAC":
                raise ValueError("FLAC license error")
            with open(sp, "w") as f:
                f.write("mock mp3 audio")
                
        mock_download_song.side_effect = mock_dl_song
        
        from download import download_track
        import asyncio
        
        result = asyncio.run(download_track("123", quality="auto", retries=2))
        
        assert result is not None
        assert result["quality_used"] == "MP3_320"
        assert result["file_extension"] == ".mp3"
        assert mock_download_song.call_count == 3  # 2 FLAC fails + 1 MP3_320 success
        
        download_dir = result["download_dir"]
        import shutil
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)

def test_download_album_fallback_mechanism():
    """Verify that download_album correctly falls back to lower quality on per-track basis when highest fails."""
    mock_album_infos = [
        {
            "SNG_ID": "123",
            "SNG_TITLE": "Track 1",
            "ART_NAME": "Test Artist",
            "TRACK_NUMBER": "1"
        },
        {
            "SNG_ID": "124",
            "SNG_TITLE": "Track 2",
            "ART_NAME": "Test Artist",
            "TRACK_NUMBER": "2"
        }
    ]
    
    with patch("download.get_song_infos_from_deezer_website", return_value=mock_album_infos), \
         patch("download.get_file_format") as mock_get_file_format, \
         patch("download.download_song") as mock_download_song:
         
        mock_get_file_format.side_effect = [
            (".flac", "FLAC"),
            (".flac", "FLAC"),
            (".mp3", "MP3_320"),
            (".mp3", "MP3_128")
        ]
        
        def mock_dl_song(ti, df, sp):
            if ti["SNG_ID"] == "124" and df == "FLAC":
                raise ValueError("FLAC forbidden for Track 2")
            with open(sp, "w") as f:
                f.write("mock audio")
                
        mock_download_song.side_effect = mock_dl_song
        
        from download import download_album
        import asyncio
        
        results = asyncio.run(download_album("456", quality="auto", retries=2))
        
        assert len(results) == 2
        assert results[0]["quality_used"] == "FLAC"
        assert results[1]["quality_used"] == "MP3_320"
        assert mock_download_song.call_count == 4  # Track 1: 1 FLAC success; Track 2: 2 FLAC fails + 1 MP3_320 success
        
        download_dir = results[0]["download_dir"]
        import shutil
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)

def test_account_fallback_mechanism():
    """Verify that when a download fails on the first account, it rotates and succeeds with the second account."""
    import download
    
    # Save original values
    original_tokens = download.DEEZER_TOKENS
    original_index = download.CURRENT_TOKEN_INDEX
    
    mock_infos = {
        "SNG_ID": "123",
        "SNG_TITLE": "Test Title",
        "ART_NAME": "Test Artist",
        "TRACK_NUMBER": "1"
    }

    try:
        download.DEEZER_TOKENS = ["bad-token", "good-token"]
        download.CURRENT_TOKEN_INDEX = 0
        
        with patch("download.init_deezer_session") as mock_init, \
             patch("download.get_song_infos_from_deezer_website", return_value=mock_infos), \
             patch("download.get_file_format") as mock_get_file_format, \
             patch("download.download_song") as mock_download_song:
             
            mock_get_file_format.return_value = (".mp3", "MP3_320")
            
            def mock_dl_song(ti, df, sp):
                if download.CURRENT_TOKEN_INDEX == 0:
                    raise ValueError("Unauthorized or bad session")
                with open(sp, "w") as f:
                    f.write("mock mp3 audio")
                    
            mock_download_song.side_effect = mock_dl_song
            
            import asyncio
            result = asyncio.run(download.download_track("123", quality="mp3", retries=1))
            
            assert result is not None
            assert result["quality_used"] == "MP3_320"
            assert download.CURRENT_TOKEN_INDEX == 1
            mock_init.assert_any_call("", download.DEFAULT_QUALITY, "good-token")
            
            download_dir = result["download_dir"]
            import shutil
            if os.path.exists(download_dir):
                shutil.rmtree(download_dir, ignore_errors=True)
    finally:
        # Restore original values
        download.DEEZER_TOKENS = original_tokens
        download.CURRENT_TOKEN_INDEX = original_index

def test_details_endpoints():
    """Verify track and album details metadata endpoints proxy correctly."""
    mock_meta = {"id": "123", "title": "Test Title"}
    with patch("main.get_deezer_metadata", return_value=mock_meta) as mock_get:
        # Track details
        resp = client.get("/api/details/track/123", headers={"X-API-Key": "test-api-key"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test Title"
        mock_get.assert_called_with("track", "123")
        
        # Album details
        resp = client.get("/api/details/album/456", headers={"X-API-Key": "test-api-key"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test Title"
        mock_get.assert_called_with("album", "456")

def test_download_manager_queue_flow():
    """Verify download queueing and status endpoints work in memory."""
    payload = {
        "type": "track",
        "id": "123",
        "quality": "mp3",
        "title": "Test Title",
        "artist": "Test Artist",
        "cover_url": "http://example.com/cover.jpg"
    }
    
    with patch("main.download_manager.queue_track", return_value="track_123_abc") as mock_queue:
        resp = client.post("/api/downloads/queue", json=payload, headers={"X-API-Key": "test-api-key"})
        assert resp.status_code == 200
        assert resp.json()["download_id"] == "track_123_abc"
        mock_queue.assert_called_once_with("123", "mp3", "Test Title", "Test Artist", "http://example.com/cover.jpg")

    resp = client.get("/api/downloads", headers={"X-API-Key": "test-api-key"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

if __name__ == "__main__":
    print("Running isolated API integration tests...")
    try:
        test_unauthorized_access()
        print("  - test_unauthorized_access: PASSED")
        test_search_endpoint()
        print("  - test_search_endpoint: PASSED")
        test_search_tracks_endpoint()
        print("  - test_search_tracks_endpoint: PASSED")
        test_download_track_endpoint()
        print("  - test_download_track_endpoint: PASSED")
        test_download_album_endpoint()
        print("  - test_download_album_endpoint: PASSED")
        test_download_track_auto_fallback()
        print("  - test_download_track_auto_fallback: PASSED")
        test_download_album_auto_fallback()
        print("  - test_download_album_auto_fallback: PASSED")
        test_download_track_fallback_mechanism()
        print("  - test_download_track_fallback_mechanism: PASSED")
        test_download_album_fallback_mechanism()
        print("  - test_download_album_fallback_mechanism: PASSED")
        test_account_fallback_mechanism()
        print("  - test_account_fallback_mechanism: PASSED")
        test_details_endpoints()
        print("  - test_details_endpoints: PASSED")
        test_download_manager_queue_flow()
        print("  - test_download_manager_queue_flow: PASSED")
        print("\nAll isolated API integration tests passed successfully!")
    except AssertionError as e:
        print(f"\nAssertion failed during testing: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
