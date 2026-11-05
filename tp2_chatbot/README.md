# Chatbot météo avec Rasa et WeatherAPI

Chatbot conversationnel en français, construit avec **Rasa Open Source 3.6**, qui donne la météo
courante et les prévisions des villes et des **26 provinces de la République Démocratique du Congo**.
Les données viennent de l'API REST [WeatherAPI](https://www.weatherapi.com/) ; les appels sont faits
dans des actions personnalisées Python (`rasa_sdk`).

Cours : Conception de Système intelligent (CSI)
Auteur : *KABONGO ILUNGA JENOVIC & KALALA NZAJI LOUIS D'OR*

## Fonctionnalités

- Salutations, remerciements, adieux et aide.
- **Météo courante** d'une ville : condition, température, température ressentie, humidité, vent, heure de mise à jour.
- **Prévision d'une ville** (aujourd'hui, demain, après-demain) : températures min/max, condition, probabilité de pluie.
- **Prévision d'une province** : la province est rattachée à son chef-lieu, et la ville utilisée est précisée.
- **Bulletin des 26 provinces** : une ligne par province (chef-lieu, condition, min/max, probabilité de pluie).
- **Gestion des échecs** : ville introuvable, clé invalide, quota dépassé, délai dépassé, absence de connexion.
  L'utilisateur reçoit toujours un message clair, jamais une trace d'erreur.

## Prérequis

- **Python 3.10** (compatible avec Rasa 3.x)
- Une clé API gratuite WeatherAPI : <https://www.weatherapi.com/>
- Une connexion Internet

## Installation

Depuis la racine du projet :

```powershell
# 1. Créer l'environnement virtuel
py -3.10 -m venv venv

# 2. L'activer (PowerShell)
venv\Scripts\Activate.ps1
# Linux / macOS : source venv/bin/activate

# 3. Installer les dépendances
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> L'installation de Rasa est longue (plusieurs minutes).

## Configuration de la clé API

1. Copier le fichier d'exemple :
   ```powershell
   copy .env.example .env
   # Linux / macOS : cp .env.example .env
   ```
2. Ouvrir `.env` et renseigner la clé, sans guillemets ni espaces :
   ```
   WEATHERAPI_KEY=votre_cle_ici
   ```

Variable facultative : `CACHE_DUREE_SECONDES` (durée du cache des prévisions, 1800 secondes par défaut).

**Sécurité.** Le fichier `.env` est dans `.gitignore` et ne doit jamais être publié. Une clé publiée par
erreur dans un dépôt Git doit être considérée comme compromise : il faut la révoquer et en générer une
nouvelle, car supprimer le fichier dans un commit ultérieur ne suffit pas (l'historique la conserve).
La clé n'est jamais écrite dans les journaux.

## Exécution

1. Entraîner le modèle (à refaire après toute modification de `data/`, `domain.yml` ou `config.yml`) :
   ```powershell
   rasa data validate
   rasa train
   ```
2. Ouvrir **deux terminaux**, chacun avec l'environnement virtuel activé, à la racine du projet :
   ```powershell
   # Terminal 1 : serveur d'actions
   rasa run actions

   # Terminal 2 : conversation
   rasa shell
   ```

Le serveur d'actions écoute sur `http://localhost:5055` (test : `http://localhost:5055/health`).

## Exemples de conversation

| Message | Action déclenchée |
|---|---|
| `Quel temps fait-il à Goma ?` | `action_meteo_actuelle` |
| `Va-t-il pleuvoir demain à Bukavu ?` | `action_prevision_ville` |
| `Prévisions pour le Haut-Katanga` | `action_prevision_province` |
| `Bulletin météo RDC` | `action_bulletin_rdc` |
| `Que sais-tu faire ?` | `utter_aide` |

## Structure du projet

```
tp2_chatbot/
├── actions/
│   ├── __init__.py
│   ├── actions.py      # actions personnalisées Rasa
│   ├── weather.py      # client WeatherAPI (requêtes, erreurs, cache, journalisation)
│   └── provinces.py    # 26 provinces, chefs-lieux, coordonnées, synonymes
├── data/
│   ├── nlu.yml         # intentions, entités, synonymes, tables de recherche
│   ├── rules.yml
│   └── stories.yml
├── domain.yml
├── config.yml          # pipeline NLU (français) et politiques
├── endpoints.yml       # action_endpoint activé
├── credentials.yml
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Choix de conception

- **Coordonnées pour les provinces** : on interroge WeatherAPI avec `latitude,longitude` du chef-lieu
  plutôt qu'avec son nom, pour éviter toute confusion avec une ville homonyme hors de la RDC.
- **Validation des entrées** : le nom de lieu est nettoyé (longueur maximale, caractères autorisés) avant l'appel.
- **Robustesse** : chaque requête HTTP a un timeout ; les codes HTTP (400, 401, 403) et les codes d'erreur
  de WeatherAPI sont traduits en messages compréhensibles.
- **Cache** : les prévisions sont conservées en mémoire (30 minutes par défaut), ce qui limite la
  consommation du quota pour le bulletin des 26 provinces.
- **Bulletin rapide** : les 26 appels sont faits en parallèle (8 à la fois). Si une province échoue, sa ligne
  indique « données indisponibles » ; en cas d'erreur bloquante (clé, quota, réseau), un seul message est affiché.
- **Journalisation** : ville, code de retour et durée de chaque appel, sans la clé API.

## Dépannage

| Problème | Solution |
|---|---|
| `No module named 'pkg_resources'` | `python -m pip install "setuptools==69.5.1"` puis `rasa train` |
| `venv\Scripts\Activate.ps1` introuvable | Créer le `venv` (voir Installation) et vérifier le dossier courant |
| PowerShell refuse d'exécuter le script d'activation | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| « Le service météo est momentanément indisponible » | Vérifier `.env` : nom `.env` exact (pas `.env.txt`), `WEATHERAPI_KEY` renseignée |
| `An action must implement a name` | Vérifier que `actions.py` est la dernière version (classe `ActionMeteoBase` sans héritage de `Action`) |
| `0.0.0.0:5055` ne s'ouvre pas dans le navigateur | Normal : utiliser `http://localhost:5055/health` |
| Le bot ne reconnaît plus les nouvelles phrases | Relancer `rasa train` |

## Limites

- L'offre gratuite de WeatherAPI limite l'horizon de prévision (3 jours utilisés ici) et le nombre d'appels.
- Les coordonnées des chefs-lieux sont approximatives (au centième de degré).
