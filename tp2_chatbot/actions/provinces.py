"""Les 26 provinces de la RDC, leurs chefs-lieux et coordonnées.

Les coordonnées servent de paramètre q="lat,lon" pour WeatherAPI,
afin d'éviter toute ambiguïté de nom avec une ville homonyme hors RDC.
"""

import re
import unicodedata
from typing import Dict, Optional

PROVINCES_RDC = [
    {"province": "Kinshasa", "chef_lieu": "Kinshasa", "lat": -4.32, "lon": 15.31},
    {"province": "Kongo-Central", "chef_lieu": "Matadi", "lat": -5.82, "lon": 13.45},
    {"province": "Kwango", "chef_lieu": "Kenge", "lat": -4.81, "lon": 17.04},
    {"province": "Kwilu", "chef_lieu": "Bandundu", "lat": -3.32, "lon": 17.38},
    {"province": "Mai-Ndombe", "chef_lieu": "Inongo", "lat": -1.95, "lon": 18.27},
    {"province": "Équateur", "chef_lieu": "Mbandaka", "lat": 0.05, "lon": 18.26},
    {"province": "Mongala", "chef_lieu": "Lisala", "lat": 2.15, "lon": 21.52},
    {"province": "Nord-Ubangi", "chef_lieu": "Gbadolite", "lat": 4.28, "lon": 21.02},
    {"province": "Sud-Ubangi", "chef_lieu": "Gemena", "lat": 3.25, "lon": 19.77},
    {"province": "Tshuapa", "chef_lieu": "Boende", "lat": -0.22, "lon": 20.87},
    {"province": "Tshopo", "chef_lieu": "Kisangani", "lat": 0.52, "lon": 25.19},
    {"province": "Bas-Uele", "chef_lieu": "Buta", "lat": 2.80, "lon": 24.73},
    {"province": "Haut-Uele", "chef_lieu": "Isiro", "lat": 2.77, "lon": 27.62},
    {"province": "Ituri", "chef_lieu": "Bunia", "lat": 1.57, "lon": 30.25},
    {"province": "Nord-Kivu", "chef_lieu": "Goma", "lat": -1.68, "lon": 29.22},
    {"province": "Sud-Kivu", "chef_lieu": "Bukavu", "lat": -2.51, "lon": 28.86},
    {"province": "Maniema", "chef_lieu": "Kindu", "lat": -2.95, "lon": 25.92},
    {"province": "Haut-Katanga", "chef_lieu": "Lubumbashi", "lat": -11.66, "lon": 27.48},
    {"province": "Haut-Lomami", "chef_lieu": "Kamina", "lat": -8.74, "lon": 25.00},
    {"province": "Lualaba", "chef_lieu": "Kolwezi", "lat": -10.72, "lon": 25.47},
    {"province": "Tanganyika", "chef_lieu": "Kalemie", "lat": -5.95, "lon": 29.19},
    {"province": "Lomami", "chef_lieu": "Kabinda", "lat": -6.13, "lon": 24.48},
    {"province": "Kasaï", "chef_lieu": "Tshikapa", "lat": -6.42, "lon": 20.80},
    {"province": "Kasaï-Central", "chef_lieu": "Kananga", "lat": -5.90, "lon": 22.42},
    {"province": "Kasaï-Oriental", "chef_lieu": "Mbuji-Mayi", "lat": -6.14, "lon": 23.59},
    {"province": "Sankuru", "chef_lieu": "Lusambo", "lat": -4.97, "lon": 23.44},
]

# Synonymes (déjà normalisés : minuscules, sans accents ni tirets).
# Les variantes de graphie des noms officiels sont gérées par normaliser().
SYNONYMES_PROVINCES: Dict[str, str] = {
    "kin": "Kinshasa",
    "bas congo": "Kongo-Central",
    "maindombe": "Mai-Ndombe",
    "bandundu": "Kwilu",
}

# Mots à retirer en début de texte : « la province du Lualaba », « le Haut-Katanga »...
PREFIXES_A_RETIRER = (
    "la province de la ",
    "la province du ",
    "la province de l ",
    "la province de ",
    "province de la ",
    "province du ",
    "province de l ",
    "province de ",
    "la province ",
    "province ",
    "le ",
    "la ",
    "l ",
)


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, tirets/apostrophes remplacés par des espaces."""
    sans_accents = unicodedata.normalize("NFD", texte)
    sans_accents = "".join(c for c in sans_accents if unicodedata.category(c) != "Mn")
    sans_ponctuation = re.sub(r"[-_'’]", " ", sans_accents.lower())
    return re.sub(r"\s+", " ", sans_ponctuation).strip()


def _retirer_prefixes(texte_normalise: str) -> str:
    for prefixe in PREFIXES_A_RETIRER:
        if texte_normalise.startswith(prefixe):
            return texte_normalise[len(prefixe):].strip()
    return texte_normalise


# Index construit une seule fois : nom normalisé -> dictionnaire de la province
_INDEX_PROVINCES = {normaliser(p["province"]): p for p in PROVINCES_RDC}


def trouver_province(texte: str) -> Optional[dict]:
    """Retourne la province correspondant au texte, ou None si inconnue."""
    if not texte:
        return None
    nom = _retirer_prefixes(normaliser(texte))
    if nom in _INDEX_PROVINCES:
        return _INDEX_PROVINCES[nom]
    if nom in SYNONYMES_PROVINCES:
        return _INDEX_PROVINCES[normaliser(SYNONYMES_PROVINCES[nom])]
    return None


def coordonnees(province: dict) -> str:
    """Valeur du paramètre q de WeatherAPI : 'latitude,longitude'."""
    return f"{province['lat']},{province['lon']}"


if __name__ == "__main__":
    # Petit test rapide : python actions/provinces.py
    assert len(PROVINCES_RDC) == 26, "Il doit y avoir 26 provinces"
    for essai in ["Haut-Katanga", "kongo central", "Bas-Congo", "Kin",
                  "la province du Lualaba", "equateur", "Kasai Oriental", "Paris"]:
        trouve = trouver_province(essai)
        print(f"{essai!r:30} -> {trouve['province'] if trouve else None}")
