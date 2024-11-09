""" Zilean scraper module """

from typing import Dict

from loguru import logger

from program.media.item import Episode, MediaItem, Season, Show
from program.services.scrapers.shared import ScraperRequestHandler
from program.settings.manager import settings_manager
from program.utils.request import (
    HttpMethod,
    RateLimitExceeded,
    create_service_session,
    get_rate_limit_params,
)
import types



class Zilean:
    """Scraper for `Zilean`"""

    def __init__(self):
        self.key = "zilean"
        self.settings = settings_manager.settings.scraping.zilean
        self.timeout = self.settings.timeout
        rate_limit_params = get_rate_limit_params(max_calls=1, period=2) if self.settings.ratelimit else None
        session = create_service_session(rate_limit_params=rate_limit_params)
        self.request_handler = ScraperRequestHandler(session)
        self.initialized = self.validate()
        if not self.initialized:
            return
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
            url = f"http://localhost:8081/api/monitoring/health"
            response = self.request_handler.execute(HttpMethod.GET, url, timeout=self.timeout)
            return response.is_ok
        except Exception as e:
            logger.error(f"Zilean failed to initialize: {e}")
            return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the Zilean site for the given media items and update the object with scraped items"""
        try:
            return self.scrape(item)
        except RateLimitExceeded:
            logger.debug(f"Zilean rate limit exceeded for item: {item.log_string}")
        except Exception as e:
            logger.exception(f"Zilean exception thrown: {e}")
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
        """Wrapper for `Zilean` scrape method"""
        url = f"http://localhost:8081/api/riven/zilean/dmm/filtered"
        params = self._build_query_params(item)

        response = self.request_handler.execute(HttpMethod.GET, url, params=params, timeout=self.timeout)
        if not response.is_ok or not response.data:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
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
