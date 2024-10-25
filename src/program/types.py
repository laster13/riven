from dataclasses import dataclass
from datetime import datetime
from typing import Generator, Union

from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist, TraktContent
from program.downloaders import (
    AllDebridDownloader,
    RealDebridDownloader,
    TorBoxDownloader,
)
from program.libraries import SymlinkLibrary
from program.media.item import MediaItem
from program.scrapers import (
    Annatar,
    Jackett,
    Knightcrawler,
    Mediafusion,
    Orionoid,
    Scraping,
    Torrentio,
    Zilean,
)
from program.scrapers.torbox import TorBoxScraper
from program.symlink import Symlinker
from program.updaters import Updater

# Typehint classes
Scraper = Union[Scraping, Torrentio, Knightcrawler, Mediafusion, Orionoid, Jackett, Annatar, TorBoxScraper, Zilean]
Content = Union[Overseerr, PlexWatchlist, Listrr, Mdblist, TraktContent]
Downloader = Union[RealDebridDownloader, TorBoxDownloader, AllDebridDownloader]
Service = Union[Content, SymlinkLibrary, Scraper, Downloader, Symlinker, Updater]
MediaItemGenerator = Generator[MediaItem, None, MediaItem | None]

class ProcessedEvent:
    media_item: MediaItem
    service: Service
    related_media_items: list[MediaItem]


@dataclass
class Event:
    emitted_by: Service
    item_id: int
    run_at: datetime = datetime.now()