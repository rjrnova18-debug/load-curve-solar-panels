"""Static checks on the frontend files: no missing translation can reach the user."""

import json
import re
from pathlib import Path

import pytest

SRC = Path(__file__).parents[2] / "src" / "loadcurve"
WEB = SRC / "web"
LANGUAGES = ("en", "es")


def flatten(node: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat |= flatten(value, f"{path}.")
        else:
            flat[path] = value
    return flat


def messages(lang: str) -> dict[str, str]:
    return flatten(json.loads((WEB / "i18n" / f"{lang}.json").read_text(encoding="utf-8")))


def keys_used_in_frontend() -> set[str]:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    keys = set(re.findall(r'data-i18n="([\w.]+)"', html))
    for attribute_list in re.findall(r'data-i18n-attr="([^"]+)"', html):  # "aria-label: key; ..."
        keys |= {pair.split(":")[1].strip() for pair in attribute_list.split(";") if ":" in pair}
    for script in (WEB / "js").rglob("*.js"):
        keys |= set(re.findall(r'\bt\(\s*"([\w.]+)"', script.read_text(encoding="utf-8")))
    return keys


def error_codes_raised_by_the_backend() -> set[str]:
    patterns = (
        r'PydanticCustomError\(\s*"(\w+)"',
        r'LoadTableFileError\(\s*"(\w+)"',
        r'PvgisError\(\s*"(\w+)"',
        r'"code":\s*"(\w+)"',
    )
    codes: set[str] = set()
    for module in SRC.rglob("*.py"):
        text = module.read_text(encoding="utf-8")
        for pattern in patterns:
            codes |= set(re.findall(pattern, text))
    return codes


def test_both_languages_have_the_same_keys() -> None:
    assert messages("en").keys() == messages("es").keys()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_key_used_by_the_page_exists(lang: str) -> None:
    missing = keys_used_in_frontend() - messages(lang).keys()

    assert not missing


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_backend_error_code_is_translated(lang: str) -> None:
    codes = error_codes_raised_by_the_backend()
    assert len(codes) >= 10  # guards against the patterns silently matching nothing

    missing = {code for code in codes if f"errors.{code}" not in messages(lang)}

    assert not missing


@pytest.mark.parametrize("lang", LANGUAGES)
def test_placeholders_match_between_languages(lang: str) -> None:
    english = messages("en")
    for key, text in messages(lang).items():
        assert set(re.findall(r"\{(\w+)\}", text)) == set(re.findall(r"\{(\w+)\}", english[key]))
