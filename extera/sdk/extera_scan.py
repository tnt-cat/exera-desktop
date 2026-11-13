"""Static check of a plugin file: how much of it can work on desktop."""
import ast
import re

JAVA_HOOKS = ("hook_method", "hook_all_methods", "hook_all_constructors")
JAVA_PREFIXES = ("org.", "android.", "androidx.", "java.", "javax.", "com.", "de.", "kotlin.", "dalvik.")
UI_PREFIXES = ("android.", "androidx.", "org.telegram.ui.", "com.")
PHONE_CLASSES = (
    "MainTabsActivity", "pillstack", "WeatherPill", "android.hardware.", "android.app.Notification",
    "NotificationManager", "FlagSecure", "android.content.pm.", "InstantCameraView", "CameraView",
    "android.appwidget", "android.service.", "android.media.projection", "android.speech",
    "android.media.AudioRecord",
)
PHONE_NAMES = re.compile(
    r"\b(fab|pill|pills|navbar|swipe|notch|edge2edge|s-pen|spen|round|rounds|circle|circlet|"
    r"camera|flash|selfie|shortcut|shortcuts|widget|status bar|foreground|haptic|fingerprint|"
    r"overlay|gallery|attach|hidden api|termux|peek|flag secure|pocket|sensor|"
    r"кружк\w*|запись экрана|касани\w*|микрофон)\b", re.I)

WORKS = "works"
PARTIAL = "partial"
BROKEN = "broken"
PHONE = "phone"


class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.java = set()
        self.hooks = 0

    def visit_Import(self, node):
        for alias in node.names:
            self._add(alias.name, None)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self._add(node.module or "", alias.name)

    def _add(self, module, name):
        if module.startswith(JAVA_PREFIXES) and not module.startswith("org.telegram.tgnet"):
            self.java.add(module + "." + name if name else module)

    def visit_Call(self, node):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in JAVA_HOOKS:
            self.hooks += 1
        elif name in ("find_class", "jclass") and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if not arg.value.startswith("org.telegram.tgnet"):
                    self.java.add(arg.value)
        self.generic_visit(node)


_TEXTS = {
    "syntax": ("error in the plugin code: %s", "ошибка в коде плагина: %s"),
    "dex": ("contains compiled Android code", "внутри скомпилированный Android-код"),
    "phone": ("made for a phone: %s", "рассчитан на телефон: %s"),
    "hooks": ("Android method hooks: %d", "перехватов Android-методов: %d"),
    "ui": ("Android interface classes: %d", "классов Android-интерфейса: %d"),
}


def scan(source, name="", ru=False):
    """Returns (status, reason)."""
    def text(key, *args):
        return _TEXTS[key][1 if ru else 0] % args

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return BROKEN, text("syntax", e.msg)
    visitor = _Visitor()
    visitor.visit(tree)
    java = visitor.java
    if any(item.startswith("dalvik.system.") for item in java):
        return BROKEN, text("dex")
    joined = " ".join(java)
    marks = [mark for mark in PHONE_CLASSES if mark in joined]
    match = PHONE_NAMES.search(name)
    if marks or match:
        return PHONE, text("phone", ", ".join(marks[:3]) or match.group(0))
    ui = [item for item in java if item.startswith(UI_PREFIXES)]
    reasons = []
    if visitor.hooks:
        reasons.append(text("hooks", visitor.hooks))
    if ui:
        reasons.append(text("ui", len(ui)))
    if reasons:
        return PARTIAL, ", ".join(reasons)
    return WORKS, ""
