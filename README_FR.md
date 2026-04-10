# Storm Chase WebApp hébergée

## Contenu
- `app.py` : backend FastAPI
- `weather_logic.py` : logique météo et scoring V2
- `static/index.html` : interface WebApp
- `render.yaml` : déploiement Render
- `Procfile` : compatible Railway

## Déploiement Render
1. Mets ce dossier dans un dépôt GitHub.
2. Sur Render, crée un **Web Service** depuis le dépôt.
3. Render peut lire `render.yaml` automatiquement.
4. L'app sera disponible sur une URL publique.

## Déploiement Railway
1. Mets ce dossier dans un dépôt GitHub.
2. Sur Railway, crée un projet depuis ce dépôt.
3. Commande de démarrage : `uvicorn app:app --host 0.0.0.0 --port $PORT`

## Endpoints
- `/` : WebApp
- `/api/latest` : JSON météo calculé côté serveur
- `/api/health` : test rapide

## Comportement
- cache serveur 15 min
- si un refresh échoue, le backend renvoie la dernière version en cache si elle existe
