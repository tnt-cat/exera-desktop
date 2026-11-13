import extera_engine


class PluginScope:
    def __init__(self, plugin_id):
        self.plugin_id = plugin_id

    def _plugin(self):
        return extera_engine.engine.plugins.get(self.plugin_id)

    def register_cleanup(self, cleanup):
        plugin = self._plugin()
        if plugin:
            plugin.cleanups.append(cleanup)

    def close(self):
        pass


class ManagedCallback:
    def __init__(self, fn, scope=None, once=False, allow_stopped=False, cleanup_task=False):
        self._fn = fn
        self._once = once
        self._cancelled = False
        self._cancel = None

    def __call__(self, *args, **kwargs):
        if self._cancelled:
            return None
        if self._once:
            self._cancelled = True
        return self._fn(*args, **kwargs)

    def cancel(self):
        self._cancelled = True
        if self._cancel:
            self._cancel()

    @property
    def cancelled(self):
        return self._cancelled

    def set_cancel(self, cancel):
        self._cancel = cancel


def _current():
    import base_plugin

    plugin = getattr(base_plugin._loading, "plugin", None)
    return PluginScope(plugin.id) if plugin else None


def begin(plugin_id):
    return PluginScope(plugin_id)


def stop(plugin_id):
    pass


def stop_all():
    pass


def capture_scope(fn=None):
    return _current()


def cleanup_context(scope):
    import contextlib

    return contextlib.nullcontext(scope)


def bind(fn, *, once=False):
    return ManagedCallback(fn, _current(), once)


def bind_task(fn, *, once=False, scope=None):
    return ManagedCallback(fn, scope or _current(), once)


def bind_request(fn):
    return ManagedCallback(fn, _current())
