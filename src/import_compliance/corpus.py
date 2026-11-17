"""함정 코퍼스 로드 및 질의 정규화."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional

from .models import Trap

DEFAULT_CORPUS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "traps_20.json")

_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("ㆍ", "").replace("·", "")
    return _SPACE.sub(" ", text).strip()


@dataclass
class Corpus:
    version: str
    verified_on: str
    traps: List[Trap]

    def by_id(self, trap_id: str) -> Optional[Trap]:
        for trap in self.traps:
            if trap.id == trap_id:
                return trap
        return None


@lru_cache(maxsize=4)
def load_corpus(path: str = DEFAULT_CORPUS_PATH) -> Corpus:
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    traps = [Trap.from_dict(item) for item in raw["traps"]]
    ids = [t.id for t in traps]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate trap id in corpus")
    return Corpus(version=raw.get("corpus_version", "unknown"), verified_on=raw.get("verified_on", ""), traps=traps)
