import os

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
