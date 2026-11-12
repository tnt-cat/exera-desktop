from dataclasses import dataclass
from typing import Any, Callable, List


@dataclass
class Header:
    text: str
    type: str = "header"


@dataclass
class Divider:
    text: str = None
    type: str = "divider"


@dataclass
class Switch:
    key: str
    text: str
    default: bool
    subtext: str = None
    icon: str = None
    on_change: Callable = None
    on_long_click: Callable = None
    link_alias: str = None
    type: str = "switch"


@dataclass
class Selector:
    key: str
    text: str
    default: int
    items: List[str]
    icon: str = None
    on_change: Callable = None
    on_long_click: Callable = None
    link_alias: str = None
    type: str = "selector"


@dataclass
class Input:
    key: str
    text: str
    default: str = ""
    subtext: str = None
    icon: str = None
    on_change: Callable = None
    on_long_click: Callable = None
    link_alias: str = None
    type: str = "input"


@dataclass
class EditText:
    key: str
    hint: str
    default: str = ""
    multiline: bool = False
    max_length: int = 256
    mask: str = None
    on_change: Callable = None
    type: str = "edit_text"


@dataclass
class Text:
    text: str
    subtext: str = None
    icon: str = None
    accent: bool = False
    red: bool = False
    on_click: Callable = None
    create_sub_fragment: Callable = None
    on_long_click: Callable = None
    link_alias: str = None
    type: str = "text"


@dataclass
class Custom:
    item: Any = None
    view: Any = None
    factory: Any = None
    factory_args: Any = None
    on_click: Callable = None
    on_long_click: Callable = None
    create_sub_fragment: Callable = None
    link_alias: str = None
    type: str = "custom"


class SimpleSettingFactory:
    def __init__(self, create_view, bind_view, **kwargs):
        self.create_view = create_view
        self.bind_view = bind_view

    def __call__(self, *args, create_sub_fragment=None, link_alias=None):
        return Custom(factory=self, factory_args=args,
                      create_sub_fragment=create_sub_fragment, link_alias=link_alias)

    def release(self):
        pass
