from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Union
from pydantic import BaseModel
from loguru import logger
import requests
from requests.exceptions import RequestException
import time

from .shared import VIDEO_EXTENSIONS, FileFinder, DownloaderBase, premium_days_left
from program.settings.manager import settings_manager

class RDTorrentStatus(str, Enum):
    """Real-Debrid torrent status enumeration"""
    MAGNET_ERROR = "magnet_error"
    MAGNET_CONVERSION = "magnet_conversion"
    WAITING_FILES = "waiting_files_selection"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    ERROR = "error"
    SEEDING = "seeding"
    DEAD = "dead"
    UPLOADING = "uploading"
    COMPRESSING = "compressing"

class RDTorrent(BaseModel):
    """Real-Debrid torrent model"""
    id: str
    hash: str
    filename: str
    bytes: int
    status: RDTorrentStatus
    added: datetime
    links: List[str]
    ended: Optional[datetime] = None
    speed: Optional[int] = None
    seeders: Optional[int] = None

class RealDebridError(Exception):
    """Base exception for Real-Debrid related errors"""
    pass

class RealDebridAPI:
    """Handles Real-Debrid API communication"""
    BASE_URL = "https://api.real-debrid.com/rest/1.0"

    def __init__(self, api_key: str, proxy_url: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}

    def _request(self, method: str, endpoint: str, **kwargs) -> Union[dict, list]:
        """Generic request handler with error handling"""
        try:
            url = f"{self.BASE_URL}/{endpoint}"
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response: {e}")
            raise RealDebridError("Invalid JSON response") from e
        except RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

class RealDebridDownloader(DownloaderBase):
    """Main Real-Debrid downloader class implementing DownloaderBase"""
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(self):
        self.key = "realdebrid"
        self.settings = settings_manager.settings.downloaders.real_debrid
        self.api = None
        self.file_finder = None
        self.initialized = self.validate()

    def validate(self) -> bool:
        """
        Validate Real-Debrid settings and premium status
        Required by DownloaderBase
        """
        if not self._validate_settings():
            return False

        self.api = RealDebridAPI(
            api_key=self.settings.api_key,
            proxy_url=self.settings.proxy_url if self.settings.proxy_enabled else None
        )
        self.file_finder = FileFinder("filename", "filesize")

        return self._validate_premium()

    def _validate_settings(self) -> bool:
        """Validate configuration settings"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.warning("Real-Debrid API key is not set")
            return False
        if self.settings.proxy_enabled and not self.settings.proxy_url:
            logger.error("Proxy is enabled but no proxy URL is provided")
            return False
        return True

    def _validate_premium(self) -> bool:
        """Validate premium status"""
        try:
            user_info = self.api._request("GET", "user")
            if not user_info.get("premium"):
                logger.error("Premium membership required")
                return False

            expiration = datetime.fromisoformat(
                user_info["expiration"].replace("Z", "+00:00")
            ).replace(tzinfo=None)
            logger.info(premium_days_left(expiration))
            return True
        except Exception as e:
            logger.error(f"Failed to validate premium status: {e}")
            return False

    def get_instant_availability(self, infohashes: List[str]) -> Dict[str, list]:
        """
        Get instant availability for multiple infohashes with retry logic
        Required by DownloaderBase
        """

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.api._request(
                    "GET",
                    f"torrents/instantAvailability/{'/'.join(infohashes)}"
                )

                # Return early if response is not a dict
                if not isinstance(response, dict):
                    return {}

                # Check for empty response
                if all(isinstance(data, list) for data in response.values()):
                    logger.debug(f"Empty response received (attempt {attempt + 1}/{self.MAX_RETRIES})")
                    time.sleep(self.RETRY_DELAY)
                    continue

                return {
                    infohash: self._filter_valid_containers(data.get("rd", []))
                    for infohash, data in response.items()
                    if isinstance(data, dict) and "rd" in data
                }

            except Exception as e:
                logger.debug(f"Failed to get instant availability (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY)
                continue

        logger.debug("All retry attempts failed for instant availability")
        return {}

    def _filter_valid_containers(self, containers: List[dict]) -> List[dict]:
        """Filter and sort valid video containers"""
        valid_containers = [
            container for container in containers
            if self._contains_valid_video_files(container)
        ]
        return sorted(valid_containers, key=len, reverse=True)

    def _contains_valid_video_files(self, container: dict) -> bool:
        """Check if container has valid video files"""
        return all(
            any(
                file["filename"].endswith(ext) and "sample" not in file["filename"].lower()
                for ext in VIDEO_EXTENSIONS
            )
            for file in container.values()
        )

    def add_torrent(self, infohash: str) -> str:
        """
        Add a torrent by infohash
        Required by DownloaderBase
        """
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        try:
            magnet = f"magnet:?xt=urn:btih:{infohash}"
            response = self.api._request(
                "POST",
                "torrents/addMagnet",
                data={"magnet": magnet.lower()}
            )
            return response["id"]
        except Exception as e:
            logger.error(f"Failed to add torrent {infohash}: {e}")
            raise

    def select_files(self, torrent_id: str, files: List[str]):
        """
        Select files from a torrent
        Required by DownloaderBase
        """
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        try:
            self.api._request(
                "POST",
                f"torrents/selectFiles/{torrent_id}",
                data={"files": ",".join(files)}
            )
        except Exception as e:
            logger.error(f"Failed to select files for torrent {torrent_id}: {e}")
            raise

    def get_torrent_info(self, torrent_id: str) -> dict:
        """
        Get information about a torrent
        Required by DownloaderBase
        """
        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        try:
            return self.api._request("GET", f"torrents/info/{torrent_id}")
        except Exception as e:
            logger.error(f"Failed to get torrent info for {torrent_id}: {e}")
            raise

    def delete_torrent(self, torrent_id: str):
        """
        Delete a torrent
        Required by DownloaderBase
        """

        if not self.initialized:
            raise RealDebridError("Downloader not properly initialized")

        try:
            self.api._request("DELETE", f"torrents/delete/{torrent_id}")
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent_id}: {e}")
            raise