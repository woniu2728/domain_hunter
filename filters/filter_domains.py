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
    com_only: bool = True
    letters_only: bool = True
    require_vowel: bool = True
    no_digits: bool = True
    no_hyphen: bool = True
    max_consecutive_consonants: int = 3

    def match(self, domain: str) -> bool:
        value = domain.lower().strip()
        if self.com_only and not value.endswith(".com"):
            return False

        label = value.removesuffix(".com") if value.endswith(".com") else value.split(".", 1)[0]
        if not (self.min_length <= len(label) <= self.max_length):
            return False
        if self.letters_only and not label.isalpha():
            return False
        if self.no_digits and any(char.isdigit() for char in label):
            return False
        if self.no_hyphen and "-" in label:
            return False
        if self.require_vowel and not any(char in VOWELS for char in label):
            return False
        if self.max_consecutive_consonants > 0 and _has_consecutive_consonants(
            label, self.max_consecutive_consonants + 1
        ):
            return False
        return True


def _has_consecutive_consonants(label: str, limit: int) -> bool:
    run = 0
    for char in label:
        if char.isalpha() and char not in VOWELS:
            run += 1
            if run >= limit:
                return True
        else:
            run = 0
    return False


def filter_domains(domains: Iterable[str], filters: Iterable[Filter] | None = None) -> list[str]:
    active_filters = tuple(filters or (DefaultDomainFilter(),))
    return sorted(domain for domain in domains if all(rule.match(domain) for rule in active_filters))
