"""Drafting engines. Mock today, API tomorrow.

The mock engine exists so the whole pipeline runs end to end without a
paid key. It marks every artifact MOCK so mock output can never be
mistaken for a shippable draft. The API engine is a stub until John
picks which drafting API to pay for — compute cost is the binding
constraint (Amendment 13), so the choice is his, not assumed here.
"""
from . import config


class Draft:
    def __init__(self, brief, taste_items, engine, mock=False):
        self.brief = brief
        self.taste_items = list(taste_items)
        self.engine = engine
        self.mock = mock

    def describe(self):
        tag = "MOCK-DRAFT" if self.mock else "DRAFT"
        return f"{tag} via {self.engine} for brief: {self.brief!r} " \
               f"(taste refs: {len(self.taste_items)})"


class MockEngine:
    name = "mock"

    def draft(self, brief, taste_items):
        return Draft(brief, taste_items, self.name, mock=True)


class ApiEngine:
    name = "api"

    def draft(self, brief, taste_items):
        raise NotImplementedError(
            "No drafting API chosen yet. Set DRAFTING_ENGINE=mock for now, "
            "or plug in the chosen provider here with DRAFTING_API_KEY."
        )


def get_engine():
    if config.DRAFTING_ENGINE == "api":
        return ApiEngine()
    return MockEngine()


def draft_for(brief, taste_items):
    return get_engine().draft(brief, taste_items)
