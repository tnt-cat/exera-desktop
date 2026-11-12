import re
from dataclasses import dataclass, field

from extera_java import TLRPC

_PATTERN = re.compile(
    r"```(?:(\w+)\n)?(.+?)```|`([^`\n]+)`|\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|\|\|(.+?)\|\|"
    r"|\[([^\]]+)\]\(([^)\s]+)\)|(?<![\w*])\*([^*\n]+)\*(?![\w*])|(?<![\w_])_([^_\n]+)_(?![\w_])",
    re.S)
_KINDS = {
    2: "TL_messageEntityPre", 3: "TL_messageEntityCode", 4: "TL_messageEntityBold",
    5: "TL_messageEntityItalic", 6: "TL_messageEntityStrike", 7: "TL_messageEntitySpoiler",
    8: "TL_messageEntityTextUrl", 10: "TL_messageEntityBold", 11: "TL_messageEntityItalic",
}


def utf16_len(text):
    return len(text.encode("utf-16-le")) // 2


@dataclass
class ParsedMessage:
    text: str
    entities: list = field(default_factory=list)


def make_entity(kind, offset, length, **fields):
    entity = getattr(TLRPC, kind)()
    entity.offset = offset
    entity.length = length
    vars(entity).update(fields)
    return entity


def parse_markdown(text):
    out = []
    entities = []
    position = 0
    offset = 0
    for match in _PATTERN.finditer(text):
        before = text[position:match.start()]
        out.append(before)
        offset += utf16_len(before)
        group = next(i for i in _KINDS if match.group(i) is not None)
        inner = match.group(group)
        fields = {}
        if group == 2 and match.group(1):
            fields["language"] = match.group(1)
        if group == 8:
            fields["url"] = match.group(9)
        entities.append(make_entity(_KINDS[group], offset, utf16_len(inner), **fields))
        out.append(inner)
        offset += utf16_len(inner)
        position = match.end()
    out.append(text[position:])
    return ParsedMessage("".join(out), entities)
