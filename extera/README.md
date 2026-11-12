# extera plugin engine

Python side of the plugin system. It loads exteraGram `.plugin` files and
exposes the same module names the Android SDK does, so plugins that stay within
the high-level API run unchanged.

- `sdk/extera_engine.py` loads plugins, keeps hook registrations and runs hook
  chains. The application talks to plugins only through `engine` and replaces
  `Host` with its own implementation.
- `sdk/base_plugin.py`, `client_utils.py`, `android_utils.py`, `hook_utils.py`,
  `file_utils.py`, `ui/` and the rest mirror the exteraGram SDK modules.
- `sdk/extera_java.py` makes imports from Java packages succeed. A class with a
  desktop shim resolves to it, any other becomes a stub that raises
  `Unsupported` when used.
- `sdk/extera_shims.py` holds the shims for Telegram for Android classes.

Method hooks are stored by their Java name, for example
`org.telegram.ui.Cells.ChatMessageCell.setMessageObject`. The application
lists the names it can fire in `Host.method_hook_keys()` and calls
`engine.fire_method_hook()` at the matching places.

Run the tests with `python extera/tests/test_engine.py`.
