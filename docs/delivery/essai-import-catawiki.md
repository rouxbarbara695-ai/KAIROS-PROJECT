# Essai — Import assisté Catawiki

Ce document sert à **un essai utilisateur**, pas à une mise en production. Rien
n'est déployé, et la version décrite ci-dessous se lance à la main.

## Ce que ce parcours fait, et ne fait pas

Catawiki refuse toute requête serveur : le bord Akamai répond `403` sur tous
ses domaines, y compris `robots.txt` et les pages de lot, avec un agent honnête
comme avec un agent de navigateur. Il n'existe pas d'API publique côté
acheteur. Contourner ce contrôle est exclu.

L'import assisté est donc **le** parcours Catawiki. Vous ouvrez le lot dans
votre navigateur, où vous êtes un visiteur ordinaire, vous sélectionnez tout
(`Ctrl+A`), vous copiez (`Ctrl+C`), vous collez. Rien d'autre : ni code source,
ni outils de développement.

## Résultat mesuré sur trois lots réels

Collés le 8 septembre 2026. Le total de champs ne dit pas grand-chose ; ce qui
suit dit **quoi**.

| | Jaeger-LeCoultre Reverso | Cartier Must Vendôme | Omega Constellation |
|---|---|---|---|
| Lu correctement | 40 / 47 | 40 / 47 | 40 / 47 |
| À confirmer | 2 | 0 | 2 |
| Absent de l'annonce | 7 | 7 | 7 |
| **Incorrect** | **0** | **0** | **0** |

**Repris et exacts sur les trois** : numéro de lot, marque, modèle, référence
(brute *et* normalisée), période de production, mouvement, matériau, cadran,
bracelet, état déclaré, boîte, papiers, enchère en cours et devise, nature du
montant, nombre d'enchères, prix de réserve, estimation Catawiki (basse, haute,
devise), commission acheteur, livraison vers la France, garantie, envoi assuré,
vendeur, type et pays du vendeur, description.

**À confirmer** — proposé, pas établi :

| Lot | Champ | Pourquoi |
|---|---|---|
| Jaeger-LeCoultre | Diamètre | fiche 21 mm, description 20,7 mm |
| Jaeger-LeCoultre | Révision | « Serviced » affirmé, sans date ni justificatif |
| Omega | Diamètre | fiche 22 mm, description 22,5 mm |
| Omega | Calibre | « Caliber 1456 » lu dans une phrase, pas dans un champ |

**Absent de la source, donc absent du dossier** : calibre (sauf Omega), boucle,
pièces remplacées, expédition, retours, fuseau de clôture, ancienneté du
vendeur. Aucun n'est deviné.

**Aucune valeur incorrecte** sur les trois lots.

## Limites explicites de cette version

1. **Les photos ne sont pas importées.** Un copier-coller de texte ne transporte
   pas les images. Les trois lots en avaient 63, 8 et 8. Le lien reste
   consultable.
2. **La date de clôture n'est pas résolue.** Catawiki n'affiche jamais de date
   absolue : « Tomorrow 20:26 », « Thursday 21:58 », « Closes in 5d 17m 14s ».
   Convertir supposerait que le collage a lieu à l'instant ; il peut dater
   d'une heure, et une fin d'enchère fausse d'une heure se rate. Le texte
   affiché est conservé, la date est à saisir.

Ces deux limites sont assumées pour cette première version.

## Lancer la version d'essai

Aucune URL de prévisualisation n'est exposée : cet environnement d'exécution ne
publie pas de port sur Internet, et le faire sans authentification devant une
base de données réelle n'aurait pas de sens. La version se lance en local.

```bash
# 1. Base et cache
docker compose up -d postgres redis        # ou vos services locaux

# 2. Schéma
cd apps/api && uv run alembic -c alembic.ini upgrade head

# 3. Un compte d'essai
uv run python -c "
import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.identity.application.authentication import create_user
async def main():
    e = create_async_engine('postgresql+psycopg://kairos:kairos@localhost:5432/kairos')
    async with async_sessionmaker(bind=e)() as s:
        await create_user(s, email='vous@exemple.fr', password='un-mot-de-passe-assez-long')
    await e.dispose()
asyncio.run(main())"

# 4. L'API
uv run uvicorn app.main:app --port 8000

# 5. L'interface, dans un autre terminal
cd apps/web && pnpm build && API_INTERNAL_URL=http://127.0.0.1:8000 pnpm start
```

Puis `http://127.0.0.1:3000`.

## Essai de cinq minutes

Le seul essai qui compte : importer, corriger, enregistrer, rouvrir.

**Avant de commencer** : ouvrez un lot de montre Catawiki dans un onglet à
côté. N'importe lequel de ceux que vous suivez.

| | Ce que vous faites | Ce que vous devez voir |
|---|---|---|
| **1 min** | Connexion, puis **Nouvelle opportunité** → onglet **« Annonce en ligne »**. Collez le lien du lot et cliquez à côté du champ. | Un message dit que Catawiki protège ses pages. La zone de collage s'ouvre toute seule. **Aucun bouton « Récupérer »** — il échouerait. |
| **1 min** | Sur l'onglet Catawiki : `Ctrl+A`, `Ctrl+C`. Revenez, collez dans la zone, **« Analyser ce contenu »**. | « *N* champs lus sur Catawiki ». La liste de ce qui a été lu, celle de ce qui manque, et les avertissements — dont « ni un prix final » et « photos non reprises ». |
| **1 min** | **« Reprendre ces valeurs dans le formulaire »**. Vérifiez marque, référence, prix, pays. Corrigez un champ volontairement (par exemple la référence). | Les champs sont remplis. Votre correction remplace la valeur importée. |
| **1 min** | **« Créer l'opportunité »**. | La fiche s'ouvre. |
| **1 min** | Revenez à la liste, puis rouvrez la fiche. Descendez jusqu'au bloc **« Import assisté Catawiki »**. | Votre correction est là. À côté, ce que l'annonce disait : chaque valeur avec son origine, sa forme brute quand elle diffère, ce qui reste **à confirmer**, ce que l'annonce ne donnait pas. |

**Ce qu'il faut regarder en particulier** — c'est là que se cachent les erreurs
coûteuses :

- le montant est-il annoncé comme **enchère en cours**, et non comme prix ?
- l'**estimation Catawiki** est-elle bien à part, sans se mêler au prix ?
- le **prix de réserve** est-il celui de l'annonce ?
- la **période** (« 2010-2020 ») est-elle conservée sans devenir une année ?
- les frais de **livraison vers la France** correspondent-ils ?
- les champs **à confirmer** sont-ils ceux que vous auriez vous-même mis en
  doute ?

Si une valeur est fausse, dites-moi laquelle et sur quel lot : c'est ainsi que
les trois derniers défauts ont été trouvés.

## Procédure d'essai détaillée

1. **Se connecter** avec le compte créé.
2. **Nouvelle opportunité** → onglet **« Annonce en ligne »**.
3. **Coller le lien** d'un lot Catawiki. Sortir du champ : l'interface annonce
   aussitôt que Catawiki protège ses pages et ouvre le collage. Le bouton
   « Récupérer les informations » n'est pas proposé — il échouerait à coup sûr.
4. **Ouvrir le lot** dans un autre onglet, `Ctrl+A`, `Ctrl+C`, revenir, coller
   dans la zone, **« Analyser ce contenu »**.
5. **Lire l'aperçu** avant que quoi que ce soit n'entre dans le formulaire :
   champs lus, champs non renseignés, avertissements.
6. **« Reprendre ces valeurs dans le formulaire »**, puis corriger ce qui doit
   l'être. Une seconde analyse demandera confirmation avant d'écraser vos
   corrections.
7. **Créer l'opportunité**, quitter, rouvrir la fiche : le bloc **« Import
   assisté Catawiki »** montre ce que l'annonce affichait, champ par champ,
   avec sa provenance, sa valeur brute quand elle diffère, et ce qui reste à
   confirmer.

## Ce qui a été vérifié, et comment

| Vérification | Moyen |
|---|---|
| Extraction sur trois lots réels | tests unitaires (`test_catawiki_real_lots.py`) |
| Refus de conclure (réserve, fuseau, frais, devise) | tests unitaires |
| Routes, provenance, trace immuable | tests d'intégration API |
| **Parcours complet dans un navigateur** | **Playwright, Chromium** (`apps/web/e2e/`) |
| Coller → préremplir → corriger → enregistrer → rouvrir | **navigateur** |
| Le blocage Catawiki annoncé avant tout clic | **navigateur** |
| Une saisie manuelle n'affiche aucun relevé | **navigateur** |

Les lignes en gras ont été jouées dans un vrai navigateur, pas seulement contre
l'API.
