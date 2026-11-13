ELYX_PLUGIN_NAMESPACE = "ElyxPlugins"


def get_plugin_id(fn=None):
    import base_plugin

    plugin = getattr(base_plugin._loading, "plugin", None)
    return plugin.id if plugin else None
