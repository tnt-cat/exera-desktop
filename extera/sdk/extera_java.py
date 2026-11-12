"""Stand-ins for the Java side of exteraGram plugins.

Any import from a Java package succeeds. Names with a desktop shim resolve to
it, everything else becomes a JavaStub that raises Unsupported when used.
"""
import importlib.abc
import importlib.machinery
import sys
import time
import types

JAVA_ROOTS = ("org", "android", "androidx", "com", "java", "javax", "de", "dalvik", "kotlin")
SHIMS = {}


class Unsupported(Exception):
    pass


def shim(name):
    def register(obj):
        SHIMS[name] = obj
        try:
            obj._java_name = name
        except (AttributeError, TypeError):
            pass
        return obj
    return register


def java_name(obj):
    return getattr(obj, "_java_name", None)


class JavaMember:
    def __init__(self, owner, name):
        self.owner = owner
        self.name = name
        self._java_name = owner + "." + name

    def setAccessible(self, value):
        pass

    def getName(self):
        return self.name


class JavaStub:
    def __init__(self, name, owner=None):
        object.__setattr__(self, "_java_name", name)
        object.__setattr__(self, "_owner", owner)

    def __getattr__(self, attr):
        if attr.startswith("__") and attr.endswith("__"):
            raise AttributeError(attr)
        if attr in ("class_", "TYPE"):
            return self
        return JavaStub(self._java_name + "." + attr, self)

    def __call__(self, *args, **kwargs):
        owner = self._owner
        attr = self._java_name.rsplit(".", 1)[-1]
        if owner is not None:
            if attr == "getClass":
                return owner
            if attr in ("getDeclaredMethod", "getMethod"):
                return JavaMember(owner._java_name, str(args[0]))
            if attr in ("getDeclaredConstructor", "getConstructor"):
                return JavaMember(owner._java_name, "<init>")
            if attr in ("getDeclaredMethods", "getMethods", "getDeclaredConstructors"):
                return []
            if attr in ("getName", "getSimpleName"):
                name = owner._java_name
                return name if attr == "getName" else name.rsplit(".", 1)[-1]
        raise Unsupported(self._java_name + " is not available on desktop")

    def __mro_entries__(self, bases):
        return (object,)

    def __repr__(self):
        return "<java %s>" % self._java_name


def resolve(name):
    name = name.replace("$", ".")
    if name in SHIMS:
        return SHIMS[name]
    if name.startswith("org.telegram.tgnet."):
        tail = name.rsplit(".", 1)[-1]
        if tail == "TLRPC" or tail.startswith("TL_"):
            return SHIMS.setdefault(name, TLNamespace(tail))
    return JavaStub(name)


class JavaPackage(types.ModuleType):
    def __getattr__(self, attr):
        if attr.startswith("__") and attr.endswith("__"):
            raise AttributeError(attr)
        return resolve(self.__name__ + "." + attr)


class JavaFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path, target=None):
        if fullname.split(".")[0] in JAVA_ROOTS:
            return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
        return None

    def create_module(self, spec):
        module = JavaPackage(spec.name)
        module.__path__ = []
        return module

    def exec_module(self, module):
        pass


def install():
    if not any(isinstance(finder, JavaFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, JavaFinder())


class TLObject:
    def __repr__(self):
        return "%s(%s)" % (type(self).__name__, ", ".join(
            "%s=%r" % pair for pair in vars(self).items()))


class TLNamespace:
    def __init__(self, name):
        self._name = name
        self._classes = {}

    def __getattr__(self, attr):
        if attr.startswith("__") and attr.endswith("__"):
            raise AttributeError(attr)
        cls = self._classes.get(attr)
        if cls is None:
            cls = self._classes[attr] = type(attr, (TLObject,), {})
        return cls


SHIMS["org.telegram.tgnet.TLObject"] = TLObject
TLRPC = resolve("org.telegram.tgnet.TLRPC")


@shim("java.util.ArrayList")
class ArrayList(list):
    def add(self, *args):
        if len(args) == 2:
            self.insert(args[0], args[1])
        else:
            self.append(args[0])
        return True

    def addAll(self, items):
        self.extend(items)
        return True

    def get(self, index):
        return self[index]

    def set(self, index, value):
        old = self[index]
        self[index] = value
        return old

    def size(self):
        return len(self)

    def isEmpty(self):
        return not self

    def contains(self, value):
        return value in self

    def indexOf(self, value):
        return self.index(value) if value in self else -1

    def remove(self, value):
        if isinstance(value, int) and not isinstance(value, bool):
            return self.pop(value)
        if value in self:
            list.remove(self, value)
            return True
        return False


@shim("java.util.HashMap")
class HashMap(dict):
    def put(self, key, value):
        old = self.get(key)
        self[key] = value
        return old

    def containsKey(self, key):
        return key in self

    def remove(self, key):
        return self.pop(key, None)

    def size(self):
        return len(self)

    def isEmpty(self):
        return not self

    def keySet(self):
        return list(self.keys())

    def entrySet(self):
        return list(self.items())


class _Boxed:
    cast = int
    TYPE = None

    @classmethod
    def valueOf(cls, value):
        return cls.cast(value)

    def __new__(cls, value=0):
        return cls.cast(value)


@shim("java.lang.Integer")
class Integer(_Boxed):
    MAX_VALUE = 2 ** 31 - 1
    MIN_VALUE = -2 ** 31
    parseInt = staticmethod(int)


@shim("java.lang.Long")
class Long(_Boxed):
    MAX_VALUE = 2 ** 63 - 1
    MIN_VALUE = -2 ** 63
    parseLong = staticmethod(int)


@shim("java.lang.Float")
class Float(_Boxed):
    cast = float
    parseFloat = staticmethod(float)


@shim("java.lang.Double")
class Double(Float):
    parseDouble = staticmethod(float)


@shim("java.lang.Boolean")
class Boolean(_Boxed):
    cast = bool
    TRUE = True
    FALSE = False


@shim("java.lang.String")
class String(_Boxed):
    cast = str

    @staticmethod
    def format(template, *args):
        return template % args


@shim("java.lang.System")
class System:
    @staticmethod
    def currentTimeMillis():
        return int(time.time() * 1000)

    @staticmethod
    def nanoTime():
        return time.monotonic_ns()


for _name in ("Integer", "Long", "Float", "Double", "Boolean", "String"):
    SHIMS["java.lang." + _name].TYPE = SHIMS["java.lang." + _name]
for _name in ("java.lang.Object", "java.lang.Runnable", "java.lang.CharSequence"):
    SHIMS[_name] = object


def jclass(name):
    return resolve(name)


def dynamic_proxy(*interfaces):
    return object


def static_proxy(*args, **kwargs):
    return lambda cls: cls


def _cast(value=None, *args, **kwargs):
    return value


def jarray(element_type):
    return lambda items=(): list(items)


for _name in ("jint", "jlong", "jfloat", "jdouble", "jboolean", "jbyte", "jshort", "jchar", "cast"):
    SHIMS["java." + _name] = _cast
SHIMS.update({
    "java.jclass": jclass,
    "java.dynamic_proxy": dynamic_proxy,
    "java.static_proxy": static_proxy,
    "java.jarray": jarray,
    "java.Override": lambda *args, **kwargs: (lambda fn: fn),
    "java.method": lambda *args, **kwargs: (lambda fn: fn),
})
