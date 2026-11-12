from html.parser import HTMLParser

from markdown_utils import make_entity, parse_markdown, utf16_len

_TAGS = {
    "b": "TL_messageEntityBold", "strong": "TL_messageEntityBold",
    "i": "TL_messageEntityItalic", "em": "TL_messageEntityItalic",
    "u": "TL_messageEntityUnderline", "ins": "TL_messageEntityUnderline",
    "s": "TL_messageEntityStrike", "strike": "TL_messageEntityStrike", "del": "TL_messageEntityStrike",
    "code": "TL_messageEntityCode", "pre": "TL_messageEntityPre",
    "blockquote": "TL_messageEntityBlockquote", "tg-spoiler": "TL_messageEntitySpoiler",
    "spoiler": "TL_messageEntitySpoiler", "a": "TL_messageEntityTextUrl",
}


class _Html(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.offset = 0
        self.open = []
        self.entities = []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.handle_data("\n")
        elif tag in _TAGS:
            self.open.append((tag, self.offset, dict(attrs)))

    def handle_endtag(self, tag):
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index][0] == tag:
                _, start, attrs = self.open.pop(index)
                fields = {"url": attrs.get("href", "")} if tag == "a" else {}
                if self.offset > start:
                    self.entities.append(make_entity(_TAGS[tag], start, self.offset - start, **fields))
                break

    def handle_data(self, data):
        self.text.append(data)
        self.offset += utf16_len(data)


def parse_text(text, parse_mode="HTML", is_caption=False):
    if str(parse_mode).upper().startswith("MARKDOWN"):
        parsed = parse_markdown(text)
        return {"message": parsed.text, "entities": parsed.entities}
    parser = _Html()
    parser.feed(text)
    parser.close()
    entities = sorted(parser.entities, key=lambda entity: entity.offset)
    return {"message": "".join(parser.text), "entities": entities}
