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
        
        mock_download.assert_called_once_with("123")
        mock_copy.assert_called_once()
        mock_rmtree.assert_called_once_with("/tmp/dummy_download_dir", ignore_errors=True)

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
            "TRACK_NUMBER": "01"
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
        
        mock_download.assert_called_once_with("456")
        mock_zip.assert_called_once()
        mock_rmtree.assert_called_once_with("/tmp/dummy_album_dir", ignore_errors=True)

    try:
        os.remove("/tmp/dummy_song1.mp3")
        os.rmdir("/tmp/dummy_album_dir")
    except OSError:
        pass

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
        print("\nAll isolated API integration tests passed successfully!")
    except AssertionError as e:
        print(f"\nAssertion failed during testing: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
