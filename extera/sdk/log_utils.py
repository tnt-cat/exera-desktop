import contextlib
import enum
import time
import traceback

import extera_engine

__all__ = ("LogLevel", "LogRecord", "Logger", "get_logger", "dump")


class LogLevel(enum.IntEnum):
    VERBOSE = 2
    DEBUG = 3
    INFO = 4
    WARNING = 5
    ERROR = 6
    OFF = 100


def _coerce_level(value):
    if isinstance(value, LogLevel):
        return value
    if isinstance(value, str):
        return LogLevel[value.upper()]
    return LogLevel(value)


class LogRecord:
    def __init__(self, level, tag, message, location, tb, created):
        self.level = level
        self.tag = tag
        self.message = message
        self.location = location
        self.traceback = tb
        self.created = created

    @property
    def text(self):
        return self.message if not self.traceback else "%s\n%s" % (self.message, self.traceback)


class Logger:
    def __init__(self, tag=None, *, show_location=True):
        self._tag = tag or "plugin"
        self._level = None
        self._parent = None
        self._handlers = []

    @property
    def tag(self):
        return self._tag

    @property
    def level(self):
        return self._level

    @level.setter
    def level(self, value):
        self._level = None if value is None else _coerce_level(value)

    @property
    def effective_level(self):
        if self._level is not None:
            return self._level
        return self._parent.effective_level if self._parent else LogLevel.VERBOSE

    def is_enabled_for(self, level):
        return _coerce_level(level) >= self.effective_level

    def child(self, name):
        logger = Logger("%s.%s" % (self._tag, name))
        logger._parent = self
        return logger

    def add_handler(self, handler):
        self._handlers.append(handler)

    def remove_handler(self, handler):
        if handler in self._handlers:
            self._handlers.remove(handler)
            return True
        return False

    def log(self, level, msg, *args, exc_info=None, stacklevel=1):
        level = _coerce_level(level)
        if not self.is_enabled_for(level):
            return
        message = str(msg)
        if args:
            try:
                message = message % args
            except (TypeError, ValueError):
                message = " ".join([message] + [str(arg) for arg in args])
        tb = None
        if exc_info:
            tb = traceback.format_exc() if exc_info is True else "".join(
                traceback.format_exception(exc_info))
        record = LogRecord(level, self._tag, message, None, tb, time.time())
        extera_engine.log("[%s] %s: %s" % (self._tag, level.name[0], record.text))
        for handler in list(self._handlers):
            handler(record)

    def verbose(self, msg, *args, exc_info=None, stacklevel=1):
        self.log(LogLevel.VERBOSE, msg, *args, exc_info=exc_info)

    def debug(self, msg, *args, exc_info=None, stacklevel=1):
        self.log(LogLevel.DEBUG, msg, *args, exc_info=exc_info)

    def info(self, msg, *args, exc_info=None, stacklevel=1):
        self.log(LogLevel.INFO, msg, *args, exc_info=exc_info)

    def warning(self, msg, *args, exc_info=None, stacklevel=1):
        self.log(LogLevel.WARNING, msg, *args, exc_info=exc_info)

    def error(self, msg, *args, exc_info=None, stacklevel=1):
        self.log(LogLevel.ERROR, msg, *args, exc_info=exc_info)

    def exception(self, msg="", *args, stacklevel=1):
        self.log(LogLevel.ERROR, msg, *args, exc_info=True)

    def dump(self, obj, label=None, *, level=LogLevel.DEBUG, depth=2, max_items=20, stacklevel=1):
        text = dump(obj, depth, max_items)
        self.log(level, "%s: %s" % (label, text) if label else text)

    @contextlib.contextmanager
    def timed(self, label, level=LogLevel.DEBUG):
        started = time.monotonic()
        yield
        self.log(level, "%s: %.1f ms" % (label, (time.monotonic() - started) * 1000))


def get_logger(name=None):
    return Logger(name)


def dump(obj, depth=2, max_items=20):
    return repr(obj)
