"""Message catalogs (``ru``, ``sk``, ``en``) and helpers to translate report messages.

Catalogs are flat TOML files (``"key" = "template"``) next to this module; templates use ``str.format`` fields.
Lookup order: requested language -> English -> built-in English lint texts -> the key itself.
"""

from __future__ import annotations

import os
import tomllib
from functools import cache
from importlib import resources
from string import Formatter
from typing import Any

from logilens.lint.issue import DEFAULT_TEXT, LintIssue

LANGS = ("ru", "sk", "en")
DEFAULT_LANG = "en"


@cache
def catalog(lang: str) -> dict[str, str]:
    """Flat ``key -> template`` mapping of one language (empty for unknown languages)."""
    if lang not in LANGS:
        return {}
    text = resources.files(__package__).joinpath(f"{lang}.toml").read_text(encoding="utf-8")
    data = tomllib.loads(text)
    return {str(k): str(v) for k, v in data.items()}


def normalize_lang(lang: str | None) -> str:
    """``'RU'`` -> ``'ru'``; unknown -> the default language."""
    value = (lang or DEFAULT_LANG).strip().lower()
    return value if value in LANGS else DEFAULT_LANG


def system_lang() -> str:
    """Language of the user's locale (``LC_ALL`` / ``LC_MESSAGES`` / ``LANG``) when we have it, else English."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            code = value.split(".")[0].split("_")[0].split("-")[0].strip().lower()
            return code if code in LANGS else "en"
    return "en"


class _Safe(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def template(key: str, lang: str = DEFAULT_LANG) -> str:
    """Raw template of ``key``."""
    for source in (catalog(normalize_lang(lang)), catalog("en"), DEFAULT_TEXT):
        if key in source:
            return source[key]
    return key


def t(key: str, lang: str = DEFAULT_LANG, **params: Any) -> str:
    """Translated, formatted message (missing parameters are left as ``{name}``)."""
    text = template(key, lang)
    if not params and not any(field for _, field, _, _ in Formatter().parse(text) if field):
        return text
    try:
        return text.format_map(_Safe(params))
    except (ValueError, IndexError, AttributeError):
        return text


def _localized_params(params: dict[str, Any], lang: str) -> dict[str, Any]:
    out = dict(params)
    if out.get("direction") in ("input", "output"):
        out["direction"] = t(f"word.{out['direction']}", lang)
    return out


def issue_message(issue: LintIssue, lang: str = DEFAULT_LANG) -> str:
    return t(issue.msg_key, lang, **_localized_params(issue.params, lang))


def issue_fix(issue: LintIssue, lang: str = DEFAULT_LANG) -> str:
    return t(issue.fix_key, lang, **_localized_params(issue.params, lang))


def missing_keys(lang: str) -> list[str]:
    """Keys present in the English catalog (or lint defaults) but absent from ``lang``."""
    reference = set(catalog("en")) | set(DEFAULT_TEXT)
    return sorted(reference - set(catalog(lang)))


__all__ = ["DEFAULT_LANG", "LANGS", "catalog", "issue_fix", "issue_message", "missing_keys", "normalize_lang",
           "system_lang", "t"]
