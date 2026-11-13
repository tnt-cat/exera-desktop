from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import parse_qsl, urlsplit


class IntentsManager:
    @dataclass
    class HandlerInfo:
        callback: Callable
        scheme: Optional[str] = None
        host: Optional[str] = None
        path: Optional[str] = None
        required_path_args_names: Optional[list] = None
        priority: Optional[int] = 0
        action: Optional[str] = None
        whitelist_flags: Optional[list] = None
        blacklist_flags: Optional[list] = None
        type: Optional[str] = None
        categories: Optional[list] = None

    @dataclass
    class HandlerHandle:
        handler_id: str

        def unhandle(self):
            pass

    class HandlerNotRegistered(Exception):
        def __init__(self, handler_id):
            super().__init__("handler %s is not registered" % handler_id)

    @staticmethod
    def parse(url):
        return dict(parse_qsl(urlsplit(url).query))
