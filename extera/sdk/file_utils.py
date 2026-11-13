import dataclasses
import enum
import os
from typing import Any, Callable, Optional

import extera_engine


def _dir(name):
    path = os.path.join(extera_engine.host.data_dir(), name)
    os.makedirs(path, exist_ok=True)
    return path


def get_plugins_dir():
    return _dir("plugins")


def get_cache_dir():
    return _dir("cache")


def get_files_dir():
    return _dir("files")


def get_documents_dir():
    return _dir("documents")


def get_images_dir():
    return _dir("images")


def get_videos_dir():
    return _dir("videos")


def get_audios_dir():
    return _dir("audios")


def ensure_dir_exists(path):
    os.makedirs(path, exist_ok=True)
    return path


def read_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_file_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def write_file_bytes(path, content):
    with open(path, "wb") as f:
        f.write(content)
    return True


def delete_file(path):
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def list_dir(path, recursive=False, include_files=True, include_dirs=False, extensions=None):
    result = []
    for root, dirs, files in os.walk(path):
        if include_dirs:
            result += [os.path.join(root, name) for name in dirs]
        if include_files:
            result += [
                os.path.join(root, name) for name in files
                if not extensions or name.rsplit(".", 1)[-1].lower() in extensions]
        if not recursive:
            break
    return result


class staticproperty(property):
    def __get__(self, instance, owner=None):
        return self.fget()


class FilesController:
    class ExtensionAlreadyRegistered(Exception):
        pass

    class ExtensionNotRegistered(Exception):
        pass

    class SecretInvalid(Exception):
        def __init__(self, ext, secret):
            super().__init__("invalid secret for %s" % ext)

    class Place(enum.IntEnum):
        UNKNOWN = 1
        ChatActivity = 2
        FilteredSearchView = 3
        SharedMediaLayout = 4
        SearchDownloadsContainer = 5
        ChannelAdminLogActivity = 6

    @dataclasses.dataclass
    class OnClickArgs:
        place: Any
        file: Any
        file_name: str
        message: Any
        activity: Any
        parent_fragment: Any = None

    @dataclasses.dataclass
    class FileInfo:
        ext: str
        on_click: Callable
        whitelist_places: list = dataclasses.field(default_factory=list, kw_only=True)
        blacklist_places: list = dataclasses.field(default_factory=list, kw_only=True)
        get_icon: Optional[Callable] = dataclasses.field(default=None, kw_only=True)
