"""Desktop versions of the Telegram for Android classes plugins use most."""
import extera_engine
from extera_java import SHIMS, Unsupported, shim


def _host():
    return extera_engine.host


def host_call(name, account, method, args):
    call = getattr(_host(), "call", None)
    if call is None:
        raise Unsupported("%s.%s is not available on desktop" % (name, method))
    return call(name, account, method, args)


class HostObject:
    def __init__(self, name, account=None):
        self._name = name
        self._account = account

    def __getattr__(self, method):
        if method.startswith("__") and method.endswith("__"):
            raise AttributeError(method)
        return lambda *args: host_call(self._name, self._account, method, args)

    def __repr__(self):
        return "<%s account=%s>" % (self._name, self._account)


class Static(HostObject):
    def getInstance(self, account=None):
        return self._instance(_host().selected_account() if account is None else account)

    def _instance(self, account):
        return HostObject(self._name, account)


class _UserConfig(Static):
    MAX_ACCOUNT_COUNT = 1

    @property
    def selectedAccount(self):
        return _host().selected_account()

    def _instance(self, account):
        return _UserConfigInstance(self._name, account)


class _UserConfigInstance(HostObject):
    def getClientUserId(self):
        return _host().user_id(self._account)

    @property
    def clientUserId(self):
        return _host().user_id(self._account)


class _AndroidUtilities(Static):
    density = 1.0

    def dp(self, value):
        return int(value)

    def dpf2(self, value):
        return float(value)

    def runOnUIThread(self, fn, delay=0):
        _host().run_on_ui(getattr(fn, "run", fn), delay)

    def addToClipboard(self, text):
        _host().copy_to_clipboard(str(text))
        return True

    def isTablet(self):
        return False


class _LocaleController(Static):
    isRTL = False

    def getString(self, *args):
        return next((a for a in args if isinstance(a, str)), "")

    def formatString(self, key, res, *args):
        return str(key) % args if args else str(key)

    def _instance(self, account):
        return self


class _Browser(Static):
    def openUrl(self, context, url, *args):
        _host().open_url(str(url))


class ResId(int):
    def __new__(cls, name=""):
        value = int.__new__(cls, 0)
        value.name = name
        return value

    def __getattr__(self, attr):
        if attr.startswith("__") and attr.endswith("__"):
            raise AttributeError(attr)
        return ResId(attr)


@shim("org.telegram.messenger.SendMessagesHelper.SendMessageParams")
class SendMessageParams:
    def __init__(self, message=None, peer=0, entities=None, **fields):
        self.message = message
        self.peer = peer
        self.entities = entities
        self.caption = None
        self.replyToMsg = None
        self.replyToTopMsg = None
        self.searchLinks = True
        self.notify = True
        self.scheduleDate = 0
        self.path = None
        self.params = None
        vars(self).update(fields)

    @staticmethod
    def of(message, peer, *args):
        return SendMessageParams(message, peer)


class _SendMessagesHelper(Static):
    SendMessageParams = SendMessageParams

    def _instance(self, account):
        return _SendMessagesHelperInstance(self._name, account)


class _SendMessagesHelperInstance(HostObject):
    def sendMessage(self, params, *args):
        _host().send_message(self._account, dict(vars(params)))


SHIMS.update({
    "org.telegram.messenger.UserConfig": _UserConfig("UserConfig"),
    "org.telegram.messenger.AndroidUtilities": _AndroidUtilities("AndroidUtilities"),
    "org.telegram.messenger.LocaleController": _LocaleController("LocaleController"),
    "org.telegram.messenger.browser.Browser": _Browser("Browser"),
    "org.telegram.messenger.SendMessagesHelper": _SendMessagesHelper("SendMessagesHelper"),
    "org.telegram.messenger.R": ResId("R"),
    "org.telegram.messenger.ApplicationLoader": Static("ApplicationLoader"),
})
for _name in ("MessagesController", "MessagesStorage", "NotificationCenter", "FileLoader",
              "MediaDataController", "ContactsController", "AccountInstance", "MediaController",
              "NotificationsController", "DownloadController", "LocationController",
              "SecretChatHelper", "NotificationsSettings"):
    SHIMS["org.telegram.messenger." + _name] = Static(_name)
SHIMS["org.telegram.tgnet.ConnectionsManager"] = Static("ConnectionsManager")


def controller(name, account=None):
    return SHIMS[name].getInstance(account)
