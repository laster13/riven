import time
import threading
import types
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from typing import Dict
from program.media.item import MediaItem, Episode, Season, Show
from program.settings.manager import settings_manager
from utils.logging import logger
from utils.ratelimiter import RateLimiter, RateLimitExceeded
from utils.request import get, ping

class Yggflix:
    """Scraper pour le service Yggflix"""

    def __init__(self):
        """
        Initialise Yggflix avec la configuration extraite de settings_manager.
        """
        self.key = "yggflix"
        self.settings = settings_manager.settings.scraping.yggflix
        self.timeout = self.settings.timeout
        self.rate_limiter = RateLimiter(max_calls=1, period=3)
        self.lock = threading.Lock()  # Verrou pour éviter les appels concurrents
        self.initialized = self.validate()

        if self.initialized:
            logger.success("Yggflix initialized!")
        else:
            logger.error("Yggflix initialization failed.")

    def validate(self) -> bool:
        """Valider les paramètres de Yggflix avant utilisation."""
        if not self.settings.enabled:
            logger.error("Yggflix service is disabled in the configuration.")
            return False
        if not self.settings.api_url:
            logger.error("Yggflix API URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Yggflix timeout is not set or invalid.")
            return False
        try:
            logger.debug(f"Yggflix is using URL: {self.settings.api_url}")
            url = f"{self.settings.api_url}/api/riven/yggflix?query=test&ygg_passkey={self.settings.ygg_passkey}"
            response = ping(url=url, timeout=self.timeout, specific_rate_limiter=self.rate_limiter)
            return response.is_ok
        except Exception as e:
            logger.error(f"Yggflix failed to initialize: {e}")
            return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """
        Scrape les informations pour un élément de média donné (film, série, saison, épisode).
        Gère les erreurs liées au dépassement de la limite d'appel.
        """
        with self.lock:  # Empêche les appels concurrents
            try:
                # Utiliser un délai pour respecter la limite de taux manuellement
                time.sleep(1)  # Délai de 1 secondes entre les appels
                return self.scrape(item)
            except RateLimitExceeded:
                logger.error(f"Yggflix rate limit exceeded for {item.log_string}. Waiting before retrying...")
                time.sleep(1)  # Attendre avant de réessayer (ajustez selon vos besoins)
                return self.scrape(item)  # Réessayer après l'attente
            except Exception as e:
                logger.error(f"Yggflix exception thrown: {e}")
                return {}

    def _build_query_params(self, item: MediaItem) -> Dict[str, str]:
        """
        Construire les paramètres de requête pour l'API Yggflix.
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
        url = f"{self.settings.api_url}/api/riven/yggflix"
        params = self._build_query_params(item)
        params["ygg_passkey"] = self.settings.ygg_passkey

        try:
            response = get(url, params=params, timeout=self.timeout, specific_rate_limiter=self.rate_limiter)
            
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
            logger.warning(f"Yggflix connection timeout for {item.log_string}")
        except ReadTimeout:
            logger.warning(f"Yggflix read timeout for {item.log_string}")
        except RequestException as e:
            logger.error(f"Yggflix request exception: {str(e)}")
        except Exception as e:
            logger.error(f"Yggflix exception thrown: {e}")

        return {}
