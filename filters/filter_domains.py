from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol
import re


VOWELS = set("aeiou")
DOMAIN_RE = re.compile(r"^[a-z]+\.com$")


class Filter(Protocol):
    def match(self, domain: str) -> bool:
        ...


@dataclass(frozen=True)
class DefaultDomainFilter:
    min_length: int = 4
    max_length: int = 12

    def match(self, domain: str) -> bool:
        value = domain.lower().strip()
        if not DOMAIN_RE.match(value):
            return False

        label = value.removesuffix(".com")
        if not (self.min_length <= len(label) <= self.max_length):
            return False
        if not any(char in VOWELS for char in label):
            return False
        if _has_four_consecutive_consonants(label):
            return False
        return True


def _has_four_consecutive_consonants(label: str) -> bool:
    run = 0
    for char in label:
        if char.isalpha() and char not in VOWELS:
            run += 1
            if run >= 4:
                return True
        else:
            run = 0
    return False


def filter_domains(domains: Iterable[str], filters: Iterable[Filter] | None = None) -> list[str]:
    active_filters = tuple(filters or (DefaultDomainFilter(),))
    return sorted(domain for domain in domains if all(rule.match(domain) for rule in active_filters))
