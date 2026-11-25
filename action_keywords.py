from __future__ import annotations

import re
import unicodedata


# Match whole words after removing accents and normalizing punctuation.
_COMPONENTS = {
    "Béquille": r"bequilles?",
    "Câble": r"cables?",
    "Chaîne": r"chaines?",
    "Chambre à air": r"chambres? a air",
    "Dérailleur": r"derailleurs?",
    "Frein": r"freins?",
    "Garde-boue": r"garde bou(?:e|t)s?|gardes boues",
    "Guidon": r"gu?idons?",
    "Guidoline": r"guidolines?",
    "Panier": r"paniers?",
    "Pédale": r"pedales?",
    "Pédalier": r"pedaliers?",
    "Plaquette": r"plaquettes?",
    "Plateau": r"plateaux?",
    "Pneu": r"pneus?",
    "Roue": r"roues?|rouves?|devoilage|devoilee?s?",
    "Sonnette": r"sonnettes?",
}
_PATTERNS = {
    component: re.compile(rf"\b(?:{variants})\b")
    for component, variants in _COMPONENTS.items()
}


def find_components(action: str) -> set[str]:
    decomposed = unicodedata.normalize("NFD", action.casefold())
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    normalized = " ".join(re.findall(r"[a-z]+", unaccented))
    return {component for component, pattern in _PATTERNS.items() if pattern.search(normalized)}
