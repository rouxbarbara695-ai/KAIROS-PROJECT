# API FastAPI et migrations Alembic.
#
# **L'image reproduit la disposition du dépôt.** Ce n'est pas un détail
# d'esthétique : plusieurs chemins du projet sont relatifs et calculés depuis
# l'emplacement des fichiers.
#
#   alembic.ini      script_location = ../../infra/migrations
#   env.py           parents[2] / "apps" / "api"
#   migration 0001   parents[3] / "database" / "schema.sql"
#
# Aplatir `apps/api` à la racine de l'image — ce que faisait la version
# précédente — cassait les deux premiers : `../../infra/migrations` désignait
# `/infra/migrations`, qui n'existe pas, et le conteneur de migrations
# s'arrêtait en erreur au premier déploiement réel.
#
# On aurait pu réécrire ces chemins pour l'image. Ils auraient alors divergé de
# ceux du dépôt, et chaque nouveau chemin relatif écrit en développement aurait
# eu une chance de casser en production sans que rien ne le signale. Faire
# coïncider les deux dispositions supprime la classe entière de défauts.

FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /srv/apps/api

# Les manifestes d'abord : tant qu'ils ne changent pas, Docker réutilise la
# couche d'installation.
COPY apps/api/pyproject.toml apps/api/uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY apps/api ./
COPY infra/migrations /srv/infra/migrations
COPY database/schema.sql /srv/database/schema.sql

ENV PATH="/srv/apps/api/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
