"""Conservative, language-preserving comparison keys. Raw text stays untouched."""
import unicodedata

NORMALIZATION_VERSION = "nfc_lower_lmn_v1"


def comparison_key(value: str) -> str:
    """Keep Unicode letters, marks and numbers; punctuation becomes boundaries.

    Ampersands are boundaries in the base view. No language-specific expansion,
    suffix removal, transliteration, or accent stripping is performed here.
    SQL in audit_dataset.py implements exactly this rule.
    """
    value = unicodedata.normalize("NFC", value).lower()
    value = "".join(c if unicodedata.category(c)[0] in "LMN" else " " for c in value)
    return " ".join(value.split())


def latin_accent_key(value: str) -> str:
    """Auxiliary view: strip marks attached to Latin bases, preserve Indic marks."""
    result = []
    latin_base = False
    for char in unicodedata.normalize("NFD", value):
        category = unicodedata.category(char)
        if category[0] == "M":
            if not latin_base:
                result.append(char)
        else:
            latin_base = "LATIN" in unicodedata.name(char, "")
            result.append(char)
    return comparison_key(unicodedata.normalize("NFC", "".join(result)))


def entity_f05(truth, prediction):
    truth, prediction = set(truth), set(prediction)
    if not truth:
        return float(not prediction)
    tp = len(truth & prediction)
    fp, fn = len(prediction - truth), len(truth - prediction)
    return 1.25 * tp / (1.25 * tp + fp + 0.25 * fn)
