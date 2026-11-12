import contextlib
import time
import traceback

import extera_engine


class Logger:
    def __init__(self, name=None):
        self.name = name or "plugin"

    def _write(self, level, message):
        extera_engine.log("[%s] %s: %s" % (self.name, level, message))

    def debug(self, message):
        self._write("D", message)

    def info(self, message):
        self._write("I", message)

    def warning(self, message):
        self._write("W", message)

    def error(self, message):
        self._write("E", message)

    def verbose(self, message):
        self._write("V", message)

    def exception(self, message=""):
        self._write("E", "%s\n%s" % (message, traceback.format_exc()))

    def dump(self, obj, depth=2, max_items=20):
        self._write("D", dump(obj, depth, max_items))

    @contextlib.contextmanager
    def timed(self, label):
        started = time.monotonic()
        yield
        self._write("D", "%s: %.1f ms" % (label, (time.monotonic() - started) * 1000))


def get_logger(name=None):
    return Logger(name)


def dump(obj, depth=2, max_items=20):
    return repr(obj)
