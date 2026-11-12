import enum
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

import extera_engine
from extera_engine import PluginError  # noqa: F401
from extera_java import JavaMember, java_name

_loading = threading.local()


class HookStrategy(enum.Enum):
    DEFAULT = "DEFAULT"
    CANCEL = "CANCEL"
    MODIFY = "MODIFY"
    MODIFY_FINAL = "MODIFY_FINAL"


class AppEvent(enum.Enum):
    START = "app_start"
    STOP = "app_stop"
    PAUSE = "app_pause"
    RESUME = "app_resume"


class MenuItemType(enum.Enum):
    MESSAGE_CONTEXT_MENU = "message_context_menu"
    DRAWER_MENU = "drawer_menu"
    MAIN_MENU = "main_menu"
    CHAT_ACTION_MENU = "chat_action_menu"
    PROFILE_ACTION_MENU = "profile_action_menu"


class IntentHookType(enum.Enum):
    BEFORE = 0
    AFTER = 1


@dataclass
class HookResult:
    strategy: HookStrategy = HookStrategy.DEFAULT
    request: Any = None
    response: Any = None
    update: Any = None
    updates: Any = None
    error: Any = None
    params: Any = None


@dataclass
class MenuItemData:
    menu_type: MenuItemType
    text: str
    on_click: Callable
    item_id: Optional[str] = None
    icon: Optional[str] = None
    subtext: Optional[str] = None
    condition: Optional[str] = None
    priority: int = 0


@dataclass
class PluginMetadata:
    id: str
    name: str
    description: str
    author: str
    version: str
    icon: str
    min_version: str
    requirements: list


class HookFilter(enum.Enum):
    RESULT_IS_NULL = "result_is_null"
    RESULT_IS_TRUE = "result_is_true"
    RESULT_IS_FALSE = "result_is_false"
    RESULT_NOT_NULL = "result_not_null"

    @staticmethod
    def _make(kind, *args):
        return (kind,) + args

    ArgumentEqual = staticmethod(lambda index, value: ("arg_eq", index, value))
    ArgumentNotNull = staticmethod(lambda index: ("arg_not_null", index))
    ArgumentIsNull = staticmethod(lambda index: ("arg_null", index))
    ArgumentIsTrue = staticmethod(lambda index: ("arg_eq", index, True))
    ArgumentIsFalse = staticmethod(lambda index: ("arg_eq", index, False))
    ArgumentIsInstanceOf = staticmethod(lambda index, cls: ("arg_instance", index, cls))


def _passes(filters, param):
    for item in filters or ():
        if item == HookFilter.RESULT_IS_NULL:
            ok = param.result is None
        elif item == HookFilter.RESULT_NOT_NULL:
            ok = param.result is not None
        elif item == HookFilter.RESULT_IS_TRUE:
            ok = param.result is True
        elif item == HookFilter.RESULT_IS_FALSE:
            ok = param.result is False
        elif isinstance(item, tuple):
            value = param.args[item[1]] if item[1] < len(param.args) else None
            kind = item[0]
            if kind == "arg_eq":
                ok = value == item[2]
            elif kind == "arg_not_null":
                ok = value is not None
            elif kind == "arg_null":
                ok = value is None
            else:
                ok = isinstance(item[2], type) and isinstance(value, item[2])
        else:
            ok = True
        if not ok:
            return False
    return True


def hook_filters(*filters):
    def wrap(fn):
        fn.__hook_filters__ = list(filters)
        return fn
    return wrap


def fn_hook_filters(field_name):
    return hook_filters()


class MethodHookParam:
    def __init__(self, method, this, args, result=None):
        self.method = method
        self.thisObject = this
        self.args = args
        self.result = result
        self.returnEarly = False
        self.throwable = None

    def getResult(self):
        return self.result

    def setResult(self, value):
        self.result = value
        self.returnEarly = True

    def getThrowable(self):
        return self.throwable

    def hasThrowable(self):
        return self.throwable is not None

    def setThrowable(self, value):
        self.throwable = value


class XposedHook:
    pass


class MethodHook(XposedHook):
    def before_hooked_method(self, param):
        pass

    def after_hooked_method(self, param):
        pass


class MethodReplacement(XposedHook):
    def replace_hooked_method(self, param):
        return None


class BaseHook(MethodHook):
    def __init__(self, plugin=None, *, before=None, after=None,
                 before_filters=None, after_filters=None):
        self.plugin = plugin
        self._before = before
        self._after = after
        self.before_filters = before_filters
        self.after_filters = after_filters

    def before_hooked_method(self, param):
        if self._before:
            self._before(param)

    def after_hooked_method(self, param):
        if self._after:
            self._after(param)


class _Registered:
    def __init__(self, hook, before_filters, after_filters):
        self.hook = hook
        self.before_filters = before_filters
        self.after_filters = after_filters

    def run(self, param, after):
        hook = self.hook
        if isinstance(hook, MethodReplacement):
            if not after:
                param.setResult(hook.replace_hooked_method(param))
            return
        method = hook.after_hooked_method if after else hook.before_hooked_method
        filters = (self.after_filters if after else self.before_filters) or getattr(
            method, "__hook_filters__", None)
        if _passes(filters, param):
            method(param)


class Unhook:
    def __init__(self, entry):
        self._entry = entry

    def unhook(self):
        extera_engine.engine.remove_method_hook(self._entry)


_NULL = re.compile(r"\bnull\b")


def eval_condition(condition, context):
    if not condition:
        return True
    expr = condition.replace("&&", " and ").replace("||", " or ")
    expr = re.sub(r"!(?!=)", " not ", expr)
    expr = _NULL.sub("None", expr)
    expr = re.sub(r"\btrue\b", "True", expr)
    expr = re.sub(r"\bfalse\b", "False", expr)
    names = _Context(context)
    try:
        return eval(expr, {"__builtins__": {}}, names) is True
    except Exception:
        return False


class _Context(dict):
    def __init__(self, context):
        super().__init__(context or {})

    def __missing__(self, key):
        return None


class BasePlugin:
    def __init__(self):
        plugin = getattr(_loading, "plugin", None)
        if plugin is None:
            raise PluginError("plugins are created by the engine")
        self._plugin = plugin
        self.id = plugin.id
        self.name = plugin.meta["name"]
        self.description = plugin.meta["description"]
        self.author = plugin.meta["author"]
        self.version = plugin.meta["version"]
        self.icon = plugin.meta["icon"]
        self.enabled = True

    @property
    def _engine(self):
        return extera_engine.engine

    def on_plugin_load(self):
        pass

    def on_plugin_unload(self):
        pass

    def create_settings(self):
        return []

    def on_app_event(self, event_type):
        pass

    def pre_request_hook(self, request_name, account, request):
        return HookResult()

    def post_request_hook(self, request_name, account, response, error):
        return HookResult()

    def on_update_hook(self, update_name, account, update):
        return HookResult()

    def on_updates_hook(self, container_name, account, updates):
        return HookResult()

    def on_send_message_hook(self, account, params):
        return HookResult()

    def add_hook(self, name, match_substring=False, priority=0):
        self._engine.add_event_hook(self.id, name, match_substring, priority)

    def remove_hook(self, name):
        self._engine.remove_event_hook(self.id, name)

    def add_on_send_message_hook(self, priority=0):
        self._engine.add_send_hook(self.id, priority)

    def add_menu_item(self, menu_item_data):
        return self._engine.add_menu_item(self.id, menu_item_data)

    def remove_menu_item(self, item_id):
        return self._engine.remove_menu_item(self.id, item_id)

    def _hook(self, key, xposed_hook, priority, before, after, before_filters, after_filters):
        hook = xposed_hook if isinstance(xposed_hook, XposedHook) else BaseHook(
            self, before=before or getattr(xposed_hook, "before_hooked_method", None),
            after=after or getattr(xposed_hook, "after_hooked_method", None))
        entry = self._engine.add_method_hook(
            self.id, key, _Registered(hook, before_filters, after_filters), priority)
        return Unhook(entry)

    def hook_method(self, method_or_constructor, xposed_hook=None, priority=None, *,
                    before=None, after=None, before_filters=None, after_filters=None):
        key = java_name(method_or_constructor) if isinstance(
            method_or_constructor, JavaMember) else None
        if key is None:
            self.log("hook_method: unknown method %r" % (method_or_constructor,))
            key = "?"
        return self._hook(key, xposed_hook, priority, before, after, before_filters, after_filters)

    def hook_all_methods(self, hook_class, method_name, xposed_hook=None, priority=None, *,
                         before=None, after=None, before_filters=None, after_filters=None):
        key = "%s.%s" % (java_name(hook_class) or "?", method_name)
        return [self._hook(key, xposed_hook, priority, before, after, before_filters, after_filters)]

    def hook_all_constructors(self, hook_class, xposed_hook=None, priority=None, *,
                              before=None, after=None, before_filters=None, after_filters=None):
        return self.hook_all_methods(
            hook_class, "<init>", xposed_hook, priority, before=before, after=after,
            before_filters=before_filters, after_filters=after_filters)

    def unhook_method(self, unhook):
        if unhook:
            unhook.unhook()

    def add_file_hook(self, file_info):
        self._plugin.unsupported.append("file hook")

    def remove_file_hook(self, ext, secret):
        pass

    def add_intent_hook(self, info, type):
        self._plugin.unsupported.append("intent hook")
        return None

    def remove_intent_hook(self, handler_id):
        pass

    def register_cleanup(self, cleanup):
        self._plugin.cleanups.append(cleanup)

    @property
    def stop_event(self):
        return self._plugin.stop_event

    def get_setting(self, key, default=None):
        return self._plugin.settings().get(key, default)

    def set_setting(self, key, value, reload_settings=False):
        self._plugin.settings()[key] = value
        self._plugin.save_settings()

    def export_settings(self):
        return dict(self._plugin.settings())

    def import_settings(self, settings, reload_settings=True):
        self._plugin.settings().update(settings)
        self._plugin.save_settings()

    def client(self, account=None):
        import client_utils
        return client_utils.get_client(account)

    def log(self, message):
        extera_engine.log("[%s] %s" % (self.id, message))

    @property
    def logger(self):
        import log_utils
        return log_utils.get_logger(self.id)
