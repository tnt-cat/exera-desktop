import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from extera_java import TLRPC

__all__ = ("parse_markdown",)


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


TLRPC_ENTITIES_MAP = {
    TLEntityType.CODE: TLRPC.TL_messageEntityCode,
    TLEntityType.PRE: TLRPC.TL_messageEntityPre,
    TLEntityType.STRIKETHROUGH: TLRPC.TL_messageEntityStrike,
    TLEntityType.TEXT_LINK: TLRPC.TL_messageEntityTextUrl,
    TLEntityType.BOLD: TLRPC.TL_messageEntityBold,
    TLEntityType.ITALIC: TLRPC.TL_messageEntityItalic,
    TLEntityType.UNDERLINE: TLRPC.TL_messageEntityUnderline,
    TLEntityType.SPOILER: TLRPC.TL_messageEntitySpoiler,
    TLEntityType.CUSTOM_EMOJI: TLRPC.TL_messageEntityCustomEmoji,
}


@dataclass
class RawEntity:
    type: TLEntityType
    offset: int
    length: int
    language: Optional[str] = None
    url: Optional[str] = None
    document_id: Optional[int] = None

    def to_tlrpc_object(self):
        entity = TLRPC_ENTITIES_MAP[self.type]()
        entity.offset = self.offset
        entity.length = self.length
        if self.type == TLEntityType.PRE:
            entity.language = self.language or ""
        if self.type == TLEntityType.TEXT_LINK:
            entity.url = self.url
        if self.type == TLEntityType.CUSTOM_EMOJI:
            entity.document_id = self.document_id
        return entity


@dataclass
class ParsedMessage:
    text: str
    entities: Tuple[RawEntity, ...]


def to_utf16_len(s):
    return len(s.encode("utf-16-le")) // 2


def count_chars_until(string, stop_chars, start_index=0):
    count = 0
    for char in string[start_index:]:
        if char in stop_chars:
            break
        count += 1
    return count


_PATTERN = re.compile(
    r"```(?:(\w+)\n)?(.+?)```|`([^`\n]+)`|\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|\|\|(.+?)\|\|"
    r"|!\[([^\]]+)\]\((\d+)\)|\[([^\]]+)\]\(([^)\s]+)\)"
    r"|(?<![\w*])\*([^*\n]+)\*(?![\w*])|(?<![\w_])_([^_\n]+)_(?![\w_])|(?<![\w~])~([^~\n]+)~(?![\w~])",
    re.S)
_KINDS = {
    2: TLEntityType.PRE, 3: TLEntityType.CODE, 4: TLEntityType.BOLD, 5: TLEntityType.UNDERLINE,
    6: TLEntityType.STRIKETHROUGH, 7: TLEntityType.SPOILER, 8: TLEntityType.CUSTOM_EMOJI,
    10: TLEntityType.TEXT_LINK, 12: TLEntityType.BOLD, 13: TLEntityType.ITALIC,
    14: TLEntityType.STRIKETHROUGH,
}


def parse_markdown(markdown):
    out = []
    entities = []
    position = 0
    offset = 0
    for match in _PATTERN.finditer(markdown):
        before = markdown[position:match.start()]
        out.append(before)
        offset += to_utf16_len(before)
        group = next(i for i in _KINDS if match.group(i) is not None)
        inner = match.group(group)
        fields = {}
        if group == 2 and match.group(1):
            fields["language"] = match.group(1)
        elif group == 8:
            fields["document_id"] = int(match.group(9))
        elif group == 10:
            fields["url"] = match.group(11)
        entities.append(RawEntity(_KINDS[group], offset, to_utf16_len(inner), **fields))
        out.append(inner)
        offset += to_utf16_len(inner)
        position = match.end()
    out.append(markdown[position:])
    return ParsedMessage("".join(out), tuple(entities))
