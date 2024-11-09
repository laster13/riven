from typing import Dict
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from program.media.item import Episode, MediaItem, Season, Show
from program.settings.manager import settings_manager
from program.settings.models import AppModel
from loguru import logger
from utils.ratelimiter import RateLimiter, RateLimitExceeded
from utils.request import get, ping
import types

class Zilean:
    """Scraper for `Zilean`"""

    def __init__(self):
        self.key = "zilean"
        self.settings = settings_manager.settings.scraping.zilean
        self.timeout = self.settings.timeout
        self.rate_limiter = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.rate_limiter = RateLimiter(max_calls=1, period=2)
        logger.success("Zilean initialized!")

    def validate(self) -> bool:
        """Validate the Zilean settings."""
        if not self.settings.enabled:
            return False
        if not self.settings.url:
            logger.error("Zilean URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Zilean timeout is not set or invalid.")
            return False
        try:
            # Utiliser la route /health pour vérifier la disponibilité de Stream-Fusion
            url = f"{self.settings.url}/api/monitoring/health"
            response = ping(url=url, timeout=self.timeout, specific_rate_limiter=self.rate_limiter)
            return response.is_ok
        except Exception as e:
            logger.error(f"Zilean failed to initialize: {e}")
            return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the Zilean site for the given media items and update the object with scraped items"""
        try:
            return self.scrape(item)
        except RateLimitExceeded:
            self.rate_limiter.limit_hit()
        except Exception as e:
            logger.error(f"Zilean exception thrown: {e}")
        return {}

    def _build_query_params(self, item: MediaItem) -> Dict[str, str]:
        """Build the query params for the Zilean API via Stream-Fusion"""
        params = {"query": item.get_top_title()}
        if isinstance(item, MediaItem) and hasattr(item, "year"):
            params["year"] = item.year
        if isinstance(item, Show):
            params["season"] = 1
        elif isinstance(item, Season):
            params["season"] = item.number
        elif isinstance(item, Episode):
            params["season"] = item.parent.number
            params["episode"] = item.number
        return params

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Wrapper for `Zilean` scrape method using Stream-Fusion"""
        # Utilise l'URL de Stream-Fusion pour interroger Zilean via l'endpoint fonctionnel
        url = f"http://localhost:8081/api/riven/zilean/dmm/filtered"
        params = self._build_query_params(item)

        # Effectuer la requête via Stream-Fusion
        response = get(url, params=params, timeout=self.timeout, specific_rate_limiter=self.rate_limiter)
        if not response.is_ok or not response.data:
            return {}

        # Convertir la réponse si nécessaire
        if isinstance(response.data, types.SimpleNamespace):
            response_data = vars(response.data)
        else:
            response_data = response.data

        torrents: Dict[str, str] = {}

        # Vérifier que la réponse contient une clé "results" avec une liste de résultats
        if "results" in response_data and isinstance(response_data["results"], list):
            for result in response_data["results"]:
                if isinstance(result, types.SimpleNamespace):  # Convertir SimpleNamespace en dict
                    result = vars(result)

                if isinstance(result, dict):  # S'assurer que chaque résultat est maintenant un dictionnaire
                    if not result.get("raw_title") or not result.get("info_hash"):
                        continue
                    torrents[result["info_hash"]] = result["raw_title"]
                else:
                    logger.error(f"Unexpected result type in 'results': {type(result)}, result: {result}")
        else:
            logger.error(f"Expected 'results' key in response, but got: {response_data}")

        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents
