"""Taste corpus loader (Personality strand).

Amendment 13, build item 1: John's taste is the differentiator and must
be encoded as a reference corpus, or output goes generic. The corpus is
data, not code: edit data/taste_corpus.json to grow it. Every draft
records which corpus version it used, so taste drift is traceable.
"""
import json
import os

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "taste_corpus.json",
)


class TasteCorpus:
    def __init__(self, items, version):
        self.items = items
        self.version = version

    @classmethod
    def load(cls, path=DEFAULT_PATH):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data["items"], data["version"])

    def names(self):
        return [item["name"] for item in self.items]
