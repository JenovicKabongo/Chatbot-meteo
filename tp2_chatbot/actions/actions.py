"""Actions personnalisées Rasa pour le chatbot météo.
 
Chaque action :
  1. récupère les entités (ville, province, jour) ;
  2. appelle le client WeatherAPI (actions/weather.py) ;
  3. répond en français, sans jamais afficher de trace technique.
"""
 
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Text
 
from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher
 
from actions.provinces import PROVINCES_RDC, coordonnees, normaliser, trouver_province
from actions.weather import WeatherAPIError, obtenir_meteo_actuelle, obtenir_prevision
 
logger = logging.getLogger(__name__)
 
# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------
LIBELLES_JOURS = ["aujourd'hui", "demain", "après-demain"]
INDICE_AUJOURDHUI = 0
INDICE_DEMAIN = 1
INDICE_APRES_DEMAIN = 2
 
NB_THREADS_BULLETIN = 8  # appels parallèles pour le bulletin des 26 provinces
 
# Erreurs qui rendent inutile de continuer le bulletin (clé, quota, réseau...)
CODES_ARRET_BULLETIN = {1002, 2006, 2007, 2008, 2009, 401, 403, "TIMEOUT", "CONNEXION"}
 
MSG_VILLE_MANQUANTE = "Pour quelle ville souhaites-tu la météo ?"
MSG_PROVINCE_MANQUANTE = "Pour quelle province souhaites-tu les prévisions ?"
MSG_PROVINCE_INCONNUE = ("Je ne reconnais pas cette province. Essaie par exemple "
                         "« Haut-Katanga », « Kongo-Central » ou « Nord-Kivu ».")
MSG_ERREUR_INATTENDUE = "Désolé, une erreur est survenue. Réessaie dans un instant."
MSG_DONNEE_INDISPONIBLE = "données indisponibles"
 
 
# --------------------------------------------------------------------------
# Fonctions utilitaires
# --------------------------------------------------------------------------
def convertir_jour(texte: Optional[str]) -> int:
    """Convertit « aujourd'hui / demain / après-demain » en indice 0, 1 ou 2."""
    if not texte:
        return INDICE_AUJOURDHUI
    normalise = normaliser(texte)
    # « après-demain » contient « demain » : on le teste en premier
    if "apres" in normalise:
        return INDICE_APRES_DEMAIN
    if "demain" in normalise:
        return INDICE_DEMAIN
    return INDICE_AUJOURDHUI
 
 
def _entite(tracker: Tracker, nom: Text) -> Optional[Text]:
    """Dernière valeur de l'entité `nom` dans le message de l'utilisateur."""
    return next(tracker.get_latest_entity_values(nom), None)
 
 
def formater_meteo_actuelle(meteo: Dict[str, Any]) -> str:
    return (
        f"Météo actuelle à {meteo['lieu']} : {meteo['condition']}.\n"
        f"🌡️ Température : {meteo['temperature_c']:.0f} °C "
        f"(ressentie {meteo['ressentie_c']:.0f} °C)\n"
        f"💧 Humidité : {meteo['humidite_pct']} %\n"
        f"💨 Vent : {meteo['vent_kmh']:.0f} km/h\n"
        f"🕒 Dernière mise à jour : {meteo['derniere_maj']}"
    )
 
 
def formater_prevision(prevision: Dict[str, Any], indice_jour: int) -> str:
    return (
        f"Prévision pour {prevision['lieu']} {LIBELLES_JOURS[indice_jour]} "
        f"({prevision['date']}) : {prevision['condition']}.\n"
        f"🌡️ Min {prevision['temp_min_c']:.0f} °C / Max {prevision['temp_max_c']:.0f} °C\n"
        f"🌧️ Probabilité de pluie : {prevision['pluie_pct']} %"
    )
 
 
# --------------------------------------------------------------------------
# Classe de base : gestion commune des erreurs
# --------------------------------------------------------------------------
class ActionMeteoBase:
    """Classe utilitaire (PAS une Action Rasa) : exécute `executer()` et
    transforme toute erreur en message clair. Les vraies actions héritent
    de (ActionMeteoBase, Action)."""
 
    def executer(self, dispatcher: CollectingDispatcher,
                 tracker: Tracker) -> List[Dict[Text, Any]]:
        raise NotImplementedError
 
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            return self.executer(dispatcher, tracker)
        except WeatherAPIError as erreur:
            dispatcher.utter_message(text=erreur.message_utilisateur)
        except Exception:  # filet de sécurité : jamais de trace côté utilisateur
            logger.exception("Erreur inattendue dans %s", self.name())
            dispatcher.utter_message(text=MSG_ERREUR_INATTENDUE)
        return []
 
 
# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------
class ActionMeteoActuelle(ActionMeteoBase, Action):
    def name(self) -> Text:
        return "action_meteo_actuelle"
 
    def executer(self, dispatcher, tracker):
        ville = _entite(tracker, "ville") or tracker.get_slot("ville")
        if not ville:
            dispatcher.utter_message(text=MSG_VILLE_MANQUANTE)
            return []
        meteo = obtenir_meteo_actuelle(ville)
        dispatcher.utter_message(text=formater_meteo_actuelle(meteo))
        return [SlotSet("ville", ville)]
 
 
class ActionPrevisionVille(ActionMeteoBase, Action):
    def name(self) -> Text:
        return "action_prevision_ville"
 
    def executer(self, dispatcher, tracker):
        ville = _entite(tracker, "ville") or tracker.get_slot("ville")
        if not ville:
            dispatcher.utter_message(text=MSG_VILLE_MANQUANTE)
            return []
        indice_jour = convertir_jour(_entite(tracker, "jour"))
        prevision = obtenir_prevision(ville, indice_jour)
        dispatcher.utter_message(text=formater_prevision(prevision, indice_jour))
        return [SlotSet("ville", ville)]
 
 
class ActionPrevisionProvince(ActionMeteoBase, Action):
    def name(self) -> Text:
        return "action_prevision_province"
 
    def executer(self, dispatcher, tracker):
        texte_province = _entite(tracker, "province") or tracker.get_slot("province")
        if not texte_province:
            dispatcher.utter_message(text=MSG_PROVINCE_MANQUANTE)
            return []
        province = trouver_province(texte_province)
        if province is None:
            dispatcher.utter_message(text=MSG_PROVINCE_INCONNUE)
            return []
 
        indice_jour = convertir_jour(_entite(tracker, "jour"))
        prevision = obtenir_prevision(coordonnees(province), indice_jour)
        texte = (
            f"Province : {province['province']} "
            f"(ville utilisée : {province['chef_lieu']})\n"
            + formater_prevision(prevision, indice_jour)
        )
        dispatcher.utter_message(text=texte)
        return [SlotSet("province", province["province"])]
 
 
class ActionBulletinRdc(ActionMeteoBase, Action):
    def name(self) -> Text:
        return "action_bulletin_rdc"
 
    @staticmethod
    def _prevision_province(province: dict) -> Dict[str, Any]:
        """Prévision du jour pour une province ; ne lève jamais d'exception."""
        try:
            prevision = obtenir_prevision(coordonnees(province), INDICE_AUJOURDHUI)
            return {"province": province, "prevision": prevision, "erreur": None}
        except WeatherAPIError as erreur:
            return {"province": province, "prevision": None, "erreur": erreur}
 
    @staticmethod
    def _ligne_bulletin(resultat: Dict[str, Any]) -> str:
        province = resultat["province"]
        debut = f"• {province['province']} ({province['chef_lieu']}) : "
        prevision = resultat["prevision"]
        if prevision is None:
            return debut + MSG_DONNEE_INDISPONIBLE
        return (
            debut + f"{prevision['condition']}, "
            f"{prevision['temp_min_c']:.0f}–{prevision['temp_max_c']:.0f} °C, "
            f"pluie {prevision['pluie_pct']} %"
        )
 
    def executer(self, dispatcher, tracker):
        with ThreadPoolExecutor(max_workers=NB_THREADS_BULLETIN) as executeur:
            resultats = list(executeur.map(self._prevision_province, PROVINCES_RDC))
 
        # Erreur bloquante (clé, quota, réseau) : inutile d'afficher 26 « indisponible »
        for resultat in resultats:
            erreur = resultat["erreur"]
            if erreur is not None and erreur.code in CODES_ARRET_BULLETIN:
                dispatcher.utter_message(text=erreur.message_utilisateur)
                return []
 
        dates = [r["prevision"]["date"] for r in resultats if r["prevision"]]
        date_bulletin = dates[0] if dates else ""
        lignes = [f"Bulletin météo RDC du {date_bulletin}".strip()]
        lignes += [self._ligne_bulletin(r) for r in resultats]
        dispatcher.utter_message(text="\n".join(lignes))
        return []
