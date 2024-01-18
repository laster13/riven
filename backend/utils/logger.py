"""Logging utils"""
import datetime
import logging
import os
import re
import sys
from .settings import settings_manager as settings
import websockets
import asyncio


def get_data_path():
    main_dir = os.path.dirname(os.path.abspath(sys.modules["__main__"].__file__))
    return os.path.join(os.path.dirname(main_dir), "data")


class RedactSensitiveInfo(logging.Filter):
    """logging filter to redact sensitive info"""

    def __init__(self):
        super().__init__("redact_sensitive_info")
        self.patterns = {
            "api_key": re.compile(r"(\'api_key\'\s*:\s*\')[^\']*\'", re.IGNORECASE),
            "token": re.compile(r"(\'token\'\s*:\s*\')[^\']*\'", re.IGNORECASE),
            "user": re.compile(r"(\'user\'\s*:\s*\')[^\']*\'", re.IGNORECASE),
            "watchlist": re.compile(r"(\'watchlist\'\s*:\s*\')[^\']*\'", re.IGNORECASE),
        }

    def _redact_string(self, data):
        if isinstance(data, str):
            for key, pattern in self.patterns.items():
                data = pattern.sub(f"'{key}' : 'REDACTED'", data)
        return data

    def _redact_nested(self, data):
        if isinstance(data, dict):
            redacted_dict = {}
            for key, value in data.items():
                for key2, _ in self.patterns.items():
                    if key in key2:
                        redacted_dict[key] = "REDACTED"
                        break
                    redacted_dict[key] = value
            return redacted_dict
        if isinstance(data, list):
            return [self._redact_nested(item) for item in data]
        if isinstance(data, tuple):
            if len(data) > 0 and isinstance(data[0], str):
                return (self._redact_string(data[0]),) + tuple(
                    self._redact_nested(item) for item in data[1:]
                )
            return tuple(self._redact_nested(item) for item in data)
        if isinstance(data, str):
            return self._redact_string(data)
        return data

    def filter(self, record):
        if record.args and isinstance(record.args, tuple):
            record.args = self._redact_nested(record.args)
        return True

class WebSocketHandler(logging.Handler):
    def __init__(self, ):
        super().__init__()
        self.url = "ws://localhost:8080/logs"
        self.websocket = None
        asyncio.get_event_loop().run_until_complete(self.connect())
    
    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.url)
        except Exception:
            pass

    def emit(self, record):
        try:
            if self.websocket:
                log_message = self.format(record)
                asyncio.get_event_loop().run_until_complete(self.websocket.send(log_message))
            else:
                asyncio.get_event_loop().run_until_complete(self.connect())
        except Exception as e:
            print(f"Error sending log message to WebSocket: {e}")
            asyncio.get_event_loop().run_until_complete(self.connect())

class Logger(logging.Logger):
    """Logging class"""

    def __init__(self):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        file_name = f"iceberg-{timestamp}.log"
        data_path = get_data_path()
        self.connections = set()

        super().__init__(file_name)
        formatter = logging.Formatter(
            "[%(asctime)s | %(levelname)s] <%(module)s.%(funcName)s> - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        if not os.path.exists(data_path):
            os.mkdir(data_path)

        if not os.path.exists(os.path.join(data_path, "logs")):
            os.mkdir(os.path.join(data_path, "logs"))

        self.addFilter(RedactSensitiveInfo())

        log_level = logging.INFO
        if settings.get("debug"):
            log_level = logging.DEBUG

        if settings.get("log"):
            file_handler = logging.FileHandler(
                os.path.join(get_data_path(), "logs", file_name), encoding="utf-8"
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            self.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        self.addHandler(console_handler)

        websocket_handler = WebSocketHandler()
        websocket_handler.setLevel(log_level)
        websocket_handler.setFormatter(formatter)
        self.addHandler(websocket_handler)


logger = Logger()
