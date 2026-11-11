"""Music brick: release prep only. No distribution, no posting, no payout.

A release is distributor-ready only when its required fields are present AND
its identifiers are well-formed (ISRC format, UPC/EAN check digit).
Nothing in this module sends a song anywhere.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core import _next_id

_ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{2}\d{5}$")


def normalize_isrc(isrc: str) -> str:
    return isrc.replace("-", "").replace(" ", "").upper()


def valid_isrc(isrc: str) -> bool:
    return isinstance(isrc, str) and bool(_ISRC.match(normalize_isrc(isrc)))


def valid_gtin(code: str) -> bool:
    """UPC-A (12 digits) or EAN-13 (13 digits) with a correct check digit."""
    if not isinstance(code, str) or not code.isdigit() or len(code) not in (12, 13):
        return False
    body, check = code[:-1], int(code[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


@dataclass
class Release:
    title: str
    artist: str
    metadata_complete: bool = False
    isrc: str = ""
    upc: str = ""
    artwork_ready: bool = False
    id: str = field(default="", init=False)

    def __post_init__(self):
        if not self.title or not self.artist:
            raise ValueError("release needs a title and an artist")
        if not self.id:
            self.id = _next_id("rel")

    def problems(self) -> list[str]:
        out = []
        if not self.metadata_complete:
            out.append("metadata incomplete")
        if not self.isrc:
            out.append("ISRC missing")
        elif not valid_isrc(self.isrc):
            out.append("ISRC malformed (expected CC-XXX-YY-NNNNN)")
        if not self.upc:
            out.append("UPC missing")
        elif not valid_gtin(self.upc):
            out.append("UPC/EAN invalid (length or check digit)")
        if not self.artwork_ready:
            out.append("artwork not ready")
        return out

    def distributor_ready(self) -> bool:
        return not self.problems()

    def prep_checklist(self) -> dict[str, bool]:
        return {
            "metadata": self.metadata_complete,
            "isrc": valid_isrc(self.isrc),
            "upc": valid_gtin(self.upc),
            "artwork": self.artwork_ready,
            "distributor_ready": self.distributor_ready(),
        }

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "artist": self.artist,
                "metadata_complete": self.metadata_complete, "isrc": self.isrc,
                "upc": self.upc, "artwork_ready": self.artwork_ready}

    @classmethod
    def from_dict(cls, d: dict) -> "Release":
        r = cls(d["title"], d["artist"], bool(d["metadata_complete"]),
                d["isrc"], d["upc"], bool(d["artwork_ready"]))
        r.id = d["id"]
        return r
