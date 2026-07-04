from __future__ import annotations


def diff_deleted_domains(yesterday: set[str], today: set[str]) -> set[str]:
    return yesterday - today
