"""Emby Updater module"""
from types import SimpleNamespace
from typing import Generator

from program.settings.manager import settings_manager
from program.media.item import MediaItem
from utils.request import get, post
from loguru import logger


class EmbyUpdater:
    def __init__(self):
        self.key = "emby"
        self.initialized = False
        self.settings = settings_manager.settings.updaters.emby
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Emby Updater initialized!")

    def validate(self) -> bool:
        """Validate Emby library"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.error("Emby API key is not set!")
            return False
        if not self.settings.url:
            logger.error("Emby URL is not set!")
            return False
        try:
            response = get(f"{self.settings.url}/Users?api_key={self.settings.api_key}")
            if response.is_ok:
                self.initialized = True
                return True
        except Exception as e:
            logger.exception(f"Emby exception thrown: {e}")
        return False

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Update Emby library for a single item or a season with its episodes"""
        items_to_update = []

        if item.type in ["movie", "episode"]:
            items_to_update = [item]
        elif item.type == "show":
            for season in item.seasons:
                items_to_update += [e for e in season.episodes if e.symlinked and e.update_folder != "updated"]
        elif item.type == "season":
            items_to_update = [e for e in item.episodes if e.symlinked and e.update_folder != "updated"]

        if not items_to_update:
            logger.debug(f"No items to update for {item.log_string}")
            return

        updated = False
        updated_episodes = []

        for item_to_update in items_to_update:
            if self.update_item(item_to_update):
                updated_episodes.append(item_to_update)
                updated = True

        if updated:
            if item.type in ["show", "season"]:
                if len(updated_episodes) == len(items_to_update):
                    logger.log("EMBY", f"Updated all episodes for {item.log_string}")
                else:
                    updated_episodes_log = ", ".join([str(ep.number) for ep in updated_episodes])
                    logger.log("EMBY", f"Updated episodes {updated_episodes_log} in {item.log_string}")
            else:
                logger.log("EMBY", f"Updated {item.log_string}")

        yield item


    def update_item(self, item: MediaItem) -> bool:
        """Update the Emby item"""
        if item.symlinked and item.update_folder != "updated" and item.symlink_path:
            try:
                response = post(
                    f"{self.settings.url}/Library/Media/Updated",
                    json={"Updates": [{"Path": item.symlink_path, "UpdateType": "Created"}]},
                    params={"api_key": self.settings.api_key},
                )
                if response.is_ok:
                    return True
            except Exception as e:
                logger.error(f"Failed to update Emby item: {e}")
        return False

    # not needed to update, but maybe useful in the future?
    def get_libraries(self) -> list[SimpleNamespace]:
        """Get the libraries from Emby"""
        try:
            response = get(
                f"{self.settings.url}/Library/VirtualFolders",
                params={"api_key": self.settings.api_key},
            )
            if response.is_ok and response.data:
                return response.data
        except Exception as e:
            logger.error(f"Failed to get Emby libraries: {e}")
        return []
