import time
import threading
import types
from requests import ConnectTimeout, ReadTimeout, get
from requests.exceptions import RequestException
from typing import Dict
from program.media.item import MediaItem, Episode, Season, Show
from program.settings.manager import settings_manager
from program.services.scrapers.shared import ScraperRequestHandler
from loguru import logger
from program.utils.request import (
    HttpMethod,
    RateLimitExceeded,
    create_service_session,
    get_rate_limit_params,
)

class Sharewood:
    """Scraper pour le service Sharewood""" 

    def __init__(self):
        """
        Initialise Sharewood avec la configuration extraite de settings_manager.
        """
        self.key = "sharewood"
        self.settings = settings_manager.settings.scraping.sharewood
        self.timeout = self.settings.timeout
        rate_limit_params = get_rate_limit_params(max_calls=1, period=5) if self.settings.ratelimit else None
        session = create_service_session(rate_limit_params=rate_limit_params)
        self.request_handler = ScraperRequestHandler(session)
        self.rate_limiter = rate_limit_params
        self.initialized = self.validate()

        if self.initialized:
            logger.success("Sharewood initialized!")
        else:
            logger.error("Sharewood initialization failed.")

    def validate(self) -> bool:
        """Valider les paramètres de Sharewood avant utilisation."""
        if not self.settings.enabled:
            logger.error("Sharewood service is disabled in the configuration.")
            return False
        if not self.settings.api_url:
            logger.error("Sharewood API URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Sharewood timeout is not set or invalid.")
            return False
        try:
            logger.debug(f"Sharewood is using URL: {self.settings.api_url}")
            url = f"http://localhost:8081/api/monitoring/health"
            response = self.request_handler.execute(HttpMethod.GET, url, timeout=self.timeout)
            return response.is_ok
        except Exception as e:
            logger.error(f"Sharewood failed to initialize: {e}")
            return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """
        Scrape les informations pour un élément de média donné (film, série, saison, épisode).
        Gère les erreurs liées au dépassement de la limite d'appel.
        """
        try:
            # Utiliser un délai pour respecter la limite de taux manuellement
            return self.scrape(item)
        except RateLimitExceeded:
            logger.error(f"Sharewood rate limit exceeded for {item.log_string}. Waiting before retrying...")
        except Exception as e:
            logger.error(f"Sharewood exception thrown: {e}")
            return {}

    def _build_query_params(self, item: MediaItem) -> Dict[str, str]:
        """
        Construire les paramètres de requête pour l'API Sharewood.
        """
        params = {"query": item.get_top_title()}  # Utiliser le titre comme "query"
        
        if isinstance(item, MediaItem) and hasattr(item, "year"):
            params["year"] = item.year
        if isinstance(item, Show):
            params["type"] = "tv"
        elif isinstance(item, Season):
            params["type"] = "tv"
        elif isinstance(item, Episode):
            params["type"] = "tv"
        else:
            params["type"] = "movie"  # Par défaut pour les films

        return params

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """
        Méthode de scraping pour récupérer les torrents depuis Yggflix.
        Gère les erreurs de dépassement de limite (429 Too Many Requests).
        """
        url = f"{self.settings.api_url}/api/riven/sharewood"
        params = self._build_query_params(item)
        params["sharewood_passkey"] = self.settings.passkey

        try:
            response = self.request_handler.execute(HttpMethod.GET, url, params=params, timeout=self.timeout)
            
            if response.status_code == 429:  # API rate limit exceeded
                retry_after = response.headers.get('Retry-After', 30)  # Attendre 30s si non spécifié
                logger.warning(f"Rate limit exceeded. Retrying after {retry_after} seconds...")
                time.sleep(int(retry_after))  # Attendre avant de réessayer
                return self.scrape(item)  # Réessayer après l'attente

            if not response.is_ok or not response.data:
                logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
                return {}

            # Convertir les résultats en dict si ce sont des objets SimpleNamespace
            response_data = response.data
            if isinstance(response_data, types.SimpleNamespace):
                response_data = vars(response_data)

            # Vérification et traitement des résultats
            if not isinstance(response_data, dict) or 'results' not in response_data:
                logger.error(f"Unexpected response format from Yggflix: {response_data}")
                return {}

            torrents: Dict[str, str] = {}
            for result in response_data['results']:
                if isinstance(result, types.SimpleNamespace):
                    result = vars(result)  # Convertir SimpleNamespace en dict
                if not result.get('raw_title') or not result.get('info_hash'):
                    continue
                torrents[result['info_hash']] = result['raw_title']

            if torrents:
                logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
            else:
                logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

            return torrents

        except RateLimitExceeded:
            logger.error(f"Rate limit exceeded for {item.log_string}")
        except ConnectTimeout:
            logger.warning(f"Sharewood connection timeout for {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Sharewood read timeout for {item.log_string}")
        except RequestException as e:
            logger.error(f"Sharewood request exception: {str(e)}")
        except Exception as e:
            logger.error(f"Sharewood exception thrown: {e}")

        return {}
