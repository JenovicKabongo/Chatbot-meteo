"""Client WeatherAPI : requêtes, gestion des erreurs, cache et journalisation.

La clé API est lue depuis la variable d'environnement WEATHERAPI_KEY
(ou depuis le fichier .env). Elle n'est JAMAIS écrite dans les journaux.
"""

import logging
import os
import re
import threading
import time
from typing import Any, Dict, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()  # charge .env s'il existe

logger = logging.getLogger("weather")

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------
URL_BASE = "https://api.weatherapi.com/v1"
LANGUE = "fr"
TIMEOUT_CONNEXION_S = 3.05
TIMEOUT_LECTURE_S = 10
TIMEOUT_REQUETE = (TIMEOUT_CONNEXION_S, TIMEOUT_LECTURE_S)

NB_JOURS_PREVISION = 3          # l'offre gratuite donne quelques jours
LONGUEUR_MAX_LIEU = 60
LONGUEUR_MIN_LIEU = 2
CACHE_DUREE_S = int(os.getenv("CACHE_DUREE_SECONDES", "1800"))  # 30 minutes

# Nom de ville : lettres (accents inclus), espaces, tiret, apostrophe, point
MOTIF_NOM_LIEU = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' ’.\-]+$")
# Coordonnées : "latitude,longitude"
MOTIF_COORDONNEES = re.compile(r"^-?\d{1,3}(\.\d+)?,-?\d{1,3}(\.\d+)?$")

# --------------------------------------------------------------------------
# Messages destinés à l'utilisateur (jamais de trace technique)
# --------------------------------------------------------------------------
MSG_LIEU_INVALIDE = "Je n'ai pas compris le nom de ce lieu. Peux-tu le reformuler ?"
MSG_LIEU_INTROUVABLE = "Je ne trouve pas ce lieu. Vérifie l'orthographe ou essaie une autre ville."
MSG_CLE_INVALIDE = "Le service météo est momentanément indisponible (problème de configuration)."
MSG_QUOTA = "La limite d'utilisation du service météo est atteinte. Réessaie plus tard."
MSG_ACCES_REFUSE = "Le service météo refuse cette demande pour le moment."
MSG_TIMEOUT = "Le service météo met trop de temps à répondre. Réessaie dans un instant."
MSG_PAS_DE_CONNEXION = "Impossible de joindre le service météo. Vérifie la connexion Internet."
MSG_ERREUR_GENERIQUE = "Une erreur est survenue avec le service météo. Réessaie plus tard."
MSG_JOUR_INDISPONIBLE = "Cette prévision n'est pas disponible pour le jour demandé."

# Codes d'erreur propres à WeatherAPI -> message utilisateur
MESSAGES_PAR_CODE_API = {
    1002: MSG_CLE_INVALIDE,        # clé absente
    2006: MSG_CLE_INVALIDE,        # clé invalide
    2008: MSG_CLE_INVALIDE,        # clé désactivée
    2007: MSG_QUOTA,               # quota dépassé
    2009: MSG_ACCES_REFUSE,        # pas d'accès à cette ressource
    1003: MSG_LIEU_INVALIDE,       # paramètre q manquant
    1005: MSG_ERREUR_GENERIQUE,    # URL invalide
    1006: MSG_LIEU_INTROUVABLE,    # lieu introuvable
}

# Repli sur le code HTTP quand le JSON d'erreur est absent
MESSAGES_PAR_CODE_HTTP = {
    400: MSG_LIEU_INTROUVABLE,
    401: MSG_CLE_INVALIDE,
    403: MSG_ACCES_REFUSE,
}


class WeatherAPIError(Exception):
    """Erreur dont le message est directement affichable à l'utilisateur."""

    def __init__(self, message_utilisateur: str, code: Optional[Any] = None):
        super().__init__(message_utilisateur)
        self.message_utilisateur = message_utilisateur
        self.code = code


# --------------------------------------------------------------------------
# Validation des entrées
# --------------------------------------------------------------------------
def valider_lieu(texte: Optional[str]) -> str:
    """Nettoie et valide un nom de lieu ou des coordonnées 'lat,lon'."""
    if not texte:
        raise WeatherAPIError(MSG_LIEU_INVALIDE)
    lieu = re.sub(r"\s+", " ", str(texte)).strip()
    if not (LONGUEUR_MIN_LIEU <= len(lieu) <= LONGUEUR_MAX_LIEU):
        raise WeatherAPIError(MSG_LIEU_INVALIDE)
    if MOTIF_COORDONNEES.match(lieu.replace(" ", "")):
        return lieu.replace(" ", "")
    if not MOTIF_NOM_LIEU.match(lieu):
        raise WeatherAPIError(MSG_LIEU_INVALIDE)
    return lieu


# --------------------------------------------------------------------------
# Cache en mémoire (avec durée de vie)
# --------------------------------------------------------------------------
_cache: Dict[Tuple[str, int], Tuple[float, dict]] = {}
_verrou_cache = threading.Lock()


def _lire_cache(cle_cache: Tuple[str, int]) -> Optional[dict]:
    with _verrou_cache:
        entree = _cache.get(cle_cache)
        if entree is None:
            return None
        horodatage, donnees = entree
        if time.monotonic() - horodatage > CACHE_DUREE_S:
            del _cache[cle_cache]
            return None
        return donnees


def _ecrire_cache(cle_cache: Tuple[str, int], donnees: dict) -> None:
    with _verrou_cache:
        _cache[cle_cache] = (time.monotonic(), donnees)


def vider_cache() -> None:
    with _verrou_cache:
        _cache.clear()


# --------------------------------------------------------------------------
# Appel HTTP
# --------------------------------------------------------------------------
def _lire_cle_api() -> str:
    cle = os.getenv("WEATHERAPI_KEY")
    if not cle:
        logger.error("Variable WEATHERAPI_KEY absente")
        raise WeatherAPIError(MSG_CLE_INVALIDE)
    return cle


def _appeler_api(endpoint: str, lieu: str, **params_supplementaires: Any) -> dict:
    """Appelle un point d'accès WeatherAPI et renvoie le JSON décodé."""
    params = {"key": _lire_cle_api(), "q": lieu, "lang": LANGUE, **params_supplementaires}
    debut = time.monotonic()
    code_retour: Any = "AUCUN"
    try:
        reponse = requests.get(f"{URL_BASE}/{endpoint}.json", params=params,
                               timeout=TIMEOUT_REQUETE)
        code_retour = reponse.status_code
    except requests.Timeout:
        code_retour = "TIMEOUT"
        raise WeatherAPIError(MSG_TIMEOUT, code_retour)
    except requests.ConnectionError:
        code_retour = "CONNEXION"
        raise WeatherAPIError(MSG_PAS_DE_CONNEXION, code_retour)
    except requests.RequestException:
        code_retour = "REQUETE"
        raise WeatherAPIError(MSG_ERREUR_GENERIQUE, code_retour)
    finally:
        # On ne journalise ni la clé, ni l'URL complète, ni le message de
        # l'exception (il peut contenir l'URL avec la clé).
        logger.info("appel_api endpoint=%s lieu=%s code=%s duree=%.2fs",
                    endpoint, lieu, code_retour, time.monotonic() - debut)

    try:
        donnees = reponse.json()
    except ValueError:
        donnees = {}

    if reponse.status_code != 200 or "error" in donnees:
        code_api = (donnees.get("error") or {}).get("code")
        message = (MESSAGES_PAR_CODE_API.get(code_api)
                   or MESSAGES_PAR_CODE_HTTP.get(reponse.status_code)
                   or MSG_ERREUR_GENERIQUE)
        logger.warning("erreur_api lieu=%s http=%s code_api=%s",
                       lieu, reponse.status_code, code_api)
        raise WeatherAPIError(message, code_api or reponse.status_code)

    return donnees


# --------------------------------------------------------------------------
# Fonctions publiques
# --------------------------------------------------------------------------
def obtenir_meteo_actuelle(lieu: str) -> dict:
    """Météo courante : condition, températures, humidité, vent, mise à jour."""
    lieu = valider_lieu(lieu)
    donnees = _appeler_api("current", lieu)
    try:
        courant = donnees["current"]
        return {
            "lieu": donnees["location"]["name"],
            "pays": donnees["location"]["country"],
            "condition": courant["condition"]["text"],
            "temperature_c": courant["temp_c"],
            "ressentie_c": courant["feelslike_c"],
            "humidite_pct": courant["humidity"],
            "vent_kmh": courant["wind_kph"],
            "derniere_maj": courant["last_updated"],
        }
    except (KeyError, TypeError):
        logger.error("reponse_current_inattendue lieu=%s", lieu)
        raise WeatherAPIError(MSG_ERREUR_GENERIQUE)


def obtenir_prevision(lieu: str, indice_jour: int = 0) -> dict:
    """Prévision d'un jour (0 = aujourd'hui, 1 = demain, 2 = après-demain)."""
    lieu = valider_lieu(lieu)
    cle_cache = (lieu.lower(), NB_JOURS_PREVISION)

    donnees = _lire_cache(cle_cache)
    if donnees is None:
        donnees = _appeler_api("forecast", lieu, days=NB_JOURS_PREVISION)
        _ecrire_cache(cle_cache, donnees)
    else:
        logger.info("cache_hit lieu=%s", lieu)

    try:
        jours = donnees["forecast"]["forecastday"]
        if not 0 <= indice_jour < len(jours):
            raise WeatherAPIError(MSG_JOUR_INDISPONIBLE)
        jour = jours[indice_jour]
        return {
            "lieu": donnees["location"]["name"],
            "pays": donnees["location"]["country"],
            "date": jour["date"],
            "condition": jour["day"]["condition"]["text"],
            "temp_min_c": jour["day"]["mintemp_c"],
            "temp_max_c": jour["day"]["maxtemp_c"],
            "pluie_pct": jour["day"]["daily_chance_of_rain"],
        }
    except (KeyError, TypeError):
        logger.error("reponse_forecast_inattendue lieu=%s", lieu)
        raise WeatherAPIError(MSG_ERREUR_GENERIQUE)


if __name__ == "__main__":
    # Test rapide, depuis la racine du projet : python -m actions.weather
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
    try:
        print(obtenir_meteo_actuelle("Goma"))
        print(obtenir_prevision("-4.32,15.31", indice_jour=1))
        print(obtenir_prevision("-4.32,15.31", indice_jour=1))  # doit venir du cache
        obtenir_meteo_actuelle("Villeinexistantexyz")
    except WeatherAPIError as erreur:
        print("Message utilisateur :", erreur.message_utilisateur)
