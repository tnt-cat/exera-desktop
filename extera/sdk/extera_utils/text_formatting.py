import html
import re
from dataclasses import dataclass
from enum import Enum
from html.parser import HTMLParser
from typing import Optional

import markdown_utils
from extera_java import TLRPC

BOLD_DELIM = "*"
ITALIC_DELIM = "_"
UNDERLINE_DELIM = "__"
STRIKE_DELIM = "~"
SPOILER_DELIM = "||"
CODE_DELIM = "`"
PRE_DELIM = "```"
BLOCKQUOTE_DELIM = ">"
BLOCKQUOTE_EXPANDABLE_DELIM = "**>"
BLOCKQUOTE_EXPANDABLE_END_DELIM = "||"
FIXED_WIDTH_DELIMS = [CODE_DELIM, PRE_DELIM]
MARKDOWN_ESCAPABLE_CHARS = "\\_*[]()~`|>!"
OPENING_TAG = "<{}>"
CLOSING_TAG = "</{}>"
URL_MARKUP = '<a href="{}">{}</a>'
EMOJI_MARKUP = "<emoji id={}>{}</emoji>"


class TLEntityType(Enum):
    CODE = "code"
    PRE = "pre"
    STRIKETHROUGH = "strikethrough"
    TEXT_LINK = "text_link"
    BOLD = "bold"
    ITALIC = "italic"
    UNDERLINE = "underline"
    SPOILER = "spoiler"
    CUSTOM_EMOJI = "custom_emoji"
    BLOCKQUOTE = "blockquote"


_CLASSES = {
    TLEntityType.CODE: "TL_messageEntityCode", TLEntityType.PRE: "TL_messageEntityPre",
    TLEntityType.STRIKETHROUGH: "TL_messageEntityStrike",
    TLEntityType.TEXT_LINK: "TL_messageEntityTextUrl", TLEntityType.BOLD: "TL_messageEntityBold",
    TLEntityType.ITALIC: "TL_messageEntityItalic",
    TLEntityType.UNDERLINE: "TL_messageEntityUnderline",
    TLEntityType.SPOILER: "TL_messageEntitySpoiler",
    TLEntityType.CUSTOM_EMOJI: "TL_messageEntityCustomEmoji",
    TLEntityType.BLOCKQUOTE: "TL_messageEntityBlockquote",
}
_BY_CLASS = {name: kind for kind, name in _CLASSES.items()}
_TAGS = {
    "b": TLEntityType.BOLD, "strong": TLEntityType.BOLD, "i": TLEntityType.ITALIC,
    "em": TLEntityType.ITALIC, "u": TLEntityType.UNDERLINE, "ins": TLEntityType.UNDERLINE,
    "s": TLEntityType.STRIKETHROUGH, "strike": TLEntityType.STRIKETHROUGH,
    "del": TLEntityType.STRIKETHROUGH, "code": TLEntityType.CODE, "pre": TLEntityType.PRE,
    "blockquote": TLEntityType.BLOCKQUOTE, "tg-spoiler": TLEntityType.SPOILER,
    "spoiler": TLEntityType.SPOILER, "a": TLEntityType.TEXT_LINK,
    "emoji": TLEntityType.CUSTOM_EMOJI, "tg-emoji": TLEntityType.CUSTOM_EMOJI,
}
_HTML_NAMES = {
    TLEntityType.BOLD: "b", TLEntityType.ITALIC: "i", TLEntityType.UNDERLINE: "u",
    TLEntityType.STRIKETHROUGH: "s", TLEntityType.CODE: "code", TLEntityType.PRE: "pre",
    TLEntityType.SPOILER: "spoiler", TLEntityType.BLOCKQUOTE: "blockquote",
}
_MARKDOWN_DELIMS = {
    TLEntityType.BOLD: BOLD_DELIM, TLEntityType.ITALIC: ITALIC_DELIM,
    TLEntityType.UNDERLINE: UNDERLINE_DELIM, TLEntityType.STRIKETHROUGH: STRIKE_DELIM,
    TLEntityType.CODE: CODE_DELIM, TLEntityType.PRE: PRE_DELIM,
    TLEntityType.SPOILER: SPOILER_DELIM,
}


@dataclass
class RawEntity:
    type: TLEntityType
    offset: int
    length: int
    language: Optional[str] = None
    url: Optional[str] = None
    document_id: Optional[int] = None
    collapsed: Optional[bool] = None

    @property
    def TLRPC_ENTITIES_MAP(self):
        return {kind: getattr(TLRPC, name) for kind, name in _CLASSES.items()}

    def to_tlrpc_object(self):
        entity = getattr(TLRPC, _CLASSES[self.type])()
        entity.offset = self.offset
        entity.length = self.length
        if self.type == TLEntityType.PRE:
            entity.language = self.language or ""
        elif self.type == TLEntityType.TEXT_LINK:
            entity.url = self.url
        elif self.type == TLEntityType.CUSTOM_EMOJI:
            entity.document_id = self.document_id
        elif self.type == TLEntityType.BLOCKQUOTE:
            entity.collapsed = bool(self.collapsed)
        return entity


def add_surrogates(text):
    return re.sub(
        "[\U00010000-\U0010FFFF]",
        lambda match: "".join(
            chr(int.from_bytes(match.group().encode("utf-16-le")[i:i + 2], "little"))
            for i in (0, 2)),
        text)


def remove_surrogates(text):
    return text.encode("utf-16", "surrogatepass").decode("utf-16")


def replace_once(source, old, new, start):
    return source[:start] + source[start:].replace(old, new, 1)


class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = ""
        self.position = 0
        self.open = []
        self.entities = []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.handle_data("\n")
        elif tag in _TAGS:
            self.open.append((tag, self.position, dict(attrs)))

    def handle_endtag(self, tag):
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index][0] != tag:
                continue
            _, start, attrs = self.open.pop(index)
            if self.position > start:
                kind = _TAGS[tag]
                entity = RawEntity(kind, start, self.position - start)
                if kind == TLEntityType.TEXT_LINK:
                    entity.url = attrs.get("href", "")
                elif kind == TLEntityType.CUSTOM_EMOJI:
                    entity.document_id = int(attrs.get("id") or attrs.get("emoji-id") or 0)
                elif kind == TLEntityType.PRE:
                    entity.language = attrs.get("language", "")
                elif kind == TLEntityType.BLOCKQUOTE:
                    entity.collapsed = "expandable" in attrs
                self.entities.append(entity)
            break

    def handle_data(self, data):
        self.text += data
        self.position += markdown_utils.to_utf16_len(data)


def _result(text, entities):
    entities = sorted(entities, key=lambda entity: entity.offset)
    return {"message": text, "entities": [entity.to_tlrpc_object() for entity in entities]}


def _raw(entity):
    if isinstance(entity, (RawEntity, markdown_utils.RawEntity)):
        return TLEntityType(entity.type.value), entity
    return _BY_CLASS.get(type(entity).__name__), entity


def _unparse(text, entities, wrap):
    units = add_surrogates(text)
    inserts = []
    for item in entities or []:
        kind, entity = _raw(item)
        if kind is None:
            continue
        before, after = wrap(kind, entity)
        inserts.append((entity.offset, 1, before))
        inserts.append((entity.offset + entity.length, 0, after))
    for position, _, piece in sorted(inserts, key=lambda item: (item[0], item[1]), reverse=True):
        units = units[:position] + piece + units[position:]
    return remove_surrogates(units)


class HTML:
    @staticmethod
    def parse(text):
        parser = Parser()
        parser.feed(text)
        parser.close()
        return _result(parser.text, parser.entities)

    @staticmethod
    def unparse(text, entities):
        def wrap(kind, entity):
            if kind == TLEntityType.TEXT_LINK:
                return '<a href="%s">' % html.escape(getattr(entity, "url", "") or ""), "</a>"
            if kind == TLEntityType.CUSTOM_EMOJI:
                return "<emoji id=%s>" % getattr(entity, "document_id", 0), "</emoji>"
            name = _HTML_NAMES[kind]
            return OPENING_TAG.format(name), CLOSING_TAG.format(name)
        return _unparse(text, entities, wrap)


_MARKDOWN = re.compile(
    r"```(?:(\w+)\n)?(.+?)```|`([^`\n]+)`|\|\|(.+?)\|\||__(.+?)__"
    r"|!\[([^\]]+)\]\((\d+)\)|\[([^\]]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*|~~(.+?)~~"
    r"|(?<![\w*])\*([^*\n]+)\*(?![\w*])|(?<![\w_])_([^_\n]+)_(?![\w_])|(?<![\w~])~([^~\n]+)~(?![\w~])",
    re.S)
_MARKDOWN_KINDS = {
    2: TLEntityType.PRE, 3: TLEntityType.CODE, 4: TLEntityType.SPOILER, 5: TLEntityType.UNDERLINE,
    6: TLEntityType.CUSTOM_EMOJI, 8: TLEntityType.TEXT_LINK, 10: TLEntityType.BOLD,
    11: TLEntityType.STRIKETHROUGH, 12: TLEntityType.BOLD, 13: TLEntityType.ITALIC,
    14: TLEntityType.STRIKETHROUGH,
}


class Markdown:
    @staticmethod
    def protect_escaped_chars(text):
        escaped = {}

        def replace(match):
            key = "\x00%d\x00" % len(escaped)
            escaped[key] = match.group(1)
            return key
        return re.sub(r"\\([%s])" % re.escape(MARKDOWN_ESCAPABLE_CHARS), replace, text), escaped

    @staticmethod
    def restore_escaped_chars(text, escaped_chars):
        for key, value in escaped_chars.items():
            text = text.replace(key, value)
        return text

    @staticmethod
    def escape_and_create_quotes(text, strict):
        return text

    @classmethod
    def parse(cls, text, strict=False):
        text, escaped = cls.protect_escaped_chars(text)
        out = []
        entities = []
        position = 0
        for match in _MARKDOWN.finditer(text):
            out.append(text[position:match.start()])
            group = next(i for i in _MARKDOWN_KINDS if match.group(i) is not None)
            inner = match.group(group)
            start = len("".join(out))
            entity = RawEntity(_MARKDOWN_KINDS[group], start, len(inner))
            if group == 2:
                entity.language = match.group(1) or ""
            elif group == 6:
                entity.document_id = int(match.group(7))
            elif group == 8:
                entity.url = match.group(9)
            entities.append(entity)
            out.append(inner)
            position = match.end()
        out.append(text[position:])
        plain = "".join(out)
        for entity in entities:
            head = cls.restore_escaped_chars(plain[:entity.offset], escaped)
            body = cls.restore_escaped_chars(
                plain[entity.offset:entity.offset + entity.length], escaped)
            entity.offset = markdown_utils.to_utf16_len(head)
            entity.length = markdown_utils.to_utf16_len(body)
        return _result(cls.restore_escaped_chars(plain, escaped), entities)

    @staticmethod
    def unparse(text, entities):
        def wrap(kind, entity):
            if kind == TLEntityType.TEXT_LINK:
                return "[", "](%s)" % (getattr(entity, "url", "") or "")
            if kind == TLEntityType.CUSTOM_EMOJI:
                return "![", "](%s)" % getattr(entity, "document_id", 0)
            delim = _MARKDOWN_DELIMS.get(kind, "")
            return delim, delim
        return _unparse(text, entities, wrap)


def parse_text(text, parse_mode="HTML", is_caption=False):
    if str(parse_mode).upper().startswith("MARKDOWN"):
        return Markdown.parse(text)
    return HTML.parse(text)
