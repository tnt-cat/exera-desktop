from extera_java import Unsupported, resolve


def find_class(name):
    return resolve(name)


def get_private_field(obj, name):
    try:
        return getattr(obj, name, None)
    except Unsupported:
        return None


def set_private_field(obj, name, value):
    try:
        setattr(obj, name, value)
        return True
    except (AttributeError, Unsupported):
        return False


get_static_private_field = get_private_field
set_static_private_field = set_private_field
