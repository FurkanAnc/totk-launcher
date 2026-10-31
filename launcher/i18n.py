"""Interface language: English (default) or Turkish. Every visible string is written as t("English", "Türkçe")."""

LANGS = (("en", "English"), ("tr", "Türkçe"))
LANG = "en"


def set_lang(code: str) -> None:
    global LANG
    LANG = code if code in dict(LANGS) else "en"


def t(en: str, tr: str) -> str:
    return tr if LANG == "tr" else en
