"""Building real Java subclasses needs Android. Importing works, using does not."""
from extera_java import Unsupported


def _unsupported(name):
    def use(*args, **kwargs):
        raise Unsupported("extera_utils.classes.%s needs Android" % name)
    use.__name__ = name
    return use


def _decorator(name):
    def decorate(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return lambda fn: fn
    decorate.__name__ = name
    return decorate


class Base:
    def __init__(self, *args, **kwargs):
        raise Unsupported("extera_utils.classes.Base needs Android")

    extends = classmethod(lambda cls, *args, **kwargs: cls)


java_subclass = _decorator("java_subclass")
class_proxy = _unsupported("class_proxy")
for _name in ("jmethod", "joverride", "joverload", "jfield", "jconstructor", "jgetmethod",
              "jsetmethod", "jMVELmethod", "jMVELoverride", "jclassbuilder", "jpreconstructor",
              "jpostconstructor"):
    globals()[_name] = _decorator(_name)
