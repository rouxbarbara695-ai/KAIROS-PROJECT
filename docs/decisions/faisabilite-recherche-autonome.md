# Faisabilité de la recherche autonome de comparables — constat du 30 septembre 2026

**Statut : la fonctionnalité n'est PAS livrée, et aucun mode n'est validé de
bout en bout.** Ce document est la preuve de faisabilité demandée par la
décision « Correction de périmètre » (pas d'extension, pas d'ouverture manuelle
de site, pas de collage). Toutes les mesures viennent de **requêtes réelles**
faites avec le client de production de KAIROS (`HttpFetcher`, agent honnête,
`robots.txt` lu, 2 s entre deux requêtes, aucune nouvelle tentative après un
blocage, aucun contournement). Aucune intervention humaine n'a été nécessaire.
Preuves brutes : `faisabilite-preuves/lots-clos-catawiki-2026-09-30.json`.

## 1. Les trois lots clos, lus par leur URL

| | JLC Reverso Duetto 266.1.44 | Cartier Vendôme W1002253 | Omega Constellation 1561.61.00 |
|---|---|---|---|
| URL demandée | `…/en/l/106583853-jaeger-lecoultre-reverso-duetto-diamonds-266-1-44-serviced-women-2010-2020` | `…/en/l/106501518-cartier-must-de-cartier-vendome-no-reserve-price-w1002253-women-1990-1999` | `…/en/l/106613690-omega-constellation-no-reserve-price-1561-61-00-women-1990-1999` |
| HTTP | `308` → `…/en/l/106945165`, puis `200` (1,5 s) | `200` (0,5 s) | `200` (1,1 s) |
| Statut structuré de la page | `closed: true`, **`sold: false`**, `reservePriceMet: false`, `closeStatus: Closed` | `closed: true`, `sold: true`, `closeStatus: Closed` | `closed: true`, `sold: true`, `closeStatus: Closed` |
| Montant | 5 075 € | 1 200 € | 800 € |
| Nature du prix | dernière enchère, réserve **non atteinte** : **pas une vente** | enchère finale affichée (marteau), hors frais acheteur | enchère finale affichée (marteau), hors frais acheteur |
| Estimation Catawiki (à part) | 8 300–9 200 € | 1 200–1 400 € | 800–900 € |
| Dates | ouverture 18/09 10:00 UTC, clôture 25/09/2026 18:23 UTC | 04/09 → clôture 10/09/2026 19:58 UTC | 07/09 → clôture 13/09/2026 19:16 UTC |
| Référence identifiée | `266.1.44` (titre, description, fiche « 266.1.44 - Serviced ») | `W1002253` (titre, description, fiche) | `1561.61.00` (titre, description, fiche) |
| Manquant ou contradictoire | **Matière : description « or blanc 18 carats », fiche et sous-titre « Yellow gold ».** Le lot demandé (106583853) est redirigé vers une **republication** (106945165) : l'issue du lot d'origine n'est pas lisible. Ni boîte ni papiers. | Bracelet non d'origine (« aftermarket »). Sans papiers. Frais acheteur et pays de l'acheteur absents. | Diamètre 22 mm (fiche) contre 22,5 mm (description). Datation « circa 1998 » estimée par le vendeur. Frais acheteur absents. |

Contrôles appliqués :
- les statuts se lisent dans les **champs structurés** (`closed`, `sold`,
  `reservePriceMet`, `closeStatus`), pas dans le texte visible : les mots
  « Sold », « Reserve price not met » apparaissent dans toutes les pages, y
  compris pour un lot qui n'a pas ce statut (chaînes de traduction) ;
- Omega : la page indique `sold: true` et 800 €, comme l'a rapporté la
  recherche web de ChatGPT — **aucune divergence** ; la valeur vient de la page,
  pas d'un extrait ;
- un « vendu » affiché n'est **pas une preuve de paiement** : la classe de
  fiabilité maximale (A) ne leur est pas attribuée automatiquement. Proposition
  provisoire, à inscrire au jeu de règles : **B au plus**, jamais A tant que le
  paiement n'est pas établi ;
- déduplication : `106583853` et `106945165` sont la **même montre**
  republiée, comptée une fois ; la seule issue lisible est la non-vente à
  5 075 € (jamais un comparable de vente).

## 2. Toutes les sources interrogées par la sonde (13 sources, 39 sondages, 33,7 s)

| Source | Rôle | Résultat | Diagnostic exact | Nature de l'obstacle |
|---|---|---|---|---|
| Chrono24 | revente | **Bloquée** | `403`, `cf-mitigated: challenge` | protection technique |
| Catawiki | enchères | Accessible, **0 comparable exact** | recherche et lots `200` | contrat + absence de données (§3) |
| Watchfinder | revente | Bloquée | `robots.txt` `403` (CloudFront) | protection technique |
| Bonhams | enchères | Bloquée | `robots.txt` `403` (Cloudflare) | protection technique |
| Interenchères | enchères | Bloquée | `robots.txt` `403` (Cloudflare) | protection technique |
| Vestiaire Collective | revente | Non interrogée | `robots.txt` interdit la recherche | convention d'exclusion |
| LiveAuctioneers | enchères | Non interrogée | `robots.txt` interdit la recherche | convention d'exclusion |
| Phillips | enchères | Non interrogée | `robots.txt` interdit la recherche | convention d'exclusion |
| Christie's | enchères | Inexploitable | `200`, coquille JavaScript, aucune donnée | absence de données dans le HTML |
| Bucherer | revente | Inexploitable | `200`, coquille JavaScript | absence de données dans le HTML |
| The RealReal | revente | Inexploitable | `200`, produits à noms génériques, référence non prouvable | absence de données ; conditions interdisant les robots |
| Drouot | enchères | Inexploitable | `404`, gabarit de recherche inconnu | absence de méthode de découverte |
| 1stDibs | revente | Échec | `ReadTimeout` | technique |
| eBay | — | Non interrogée | interdit par la table d'accès `FORBIDDEN` | contrat ; l'API officielle est un autre mode (§6) |

Boutiques et archives pour les prix demandés (essai complémentaire, 26 hôtes
sondés) :

| Source | Résultat |
|---|---|
| Analog:Shift (Shopify, `products.json` autorisé) | `429` dès la page de catalogue : source arrêtée, catalogue non lu |
| Crown & Caliber, Wempe, WatchBox / 1916 Company | plan du site lisible ; **aucune URL** portant l'une des trois références |
| Chronext, Hodinkee | aucun plan du site déclaré dans `robots.txt` |
| Shop Hodinkee, Fashionphile, Tutti, Gear Patrol, Rolex Forums | défi Cloudflare (`429`/`403`) |
| Subito, Watchfinder UK | `robots.txt` `403` (Akamai / CloudFront) |
| Leboncoin, Ricardo | `403` sur le point d'accès testé |
| Marktplaats, Kleinanzeigen, 2ememain, Vinted | `robots.txt` lisible ; pas de point d'accès de catalogue public utilisable sans recherche |
| WatchUseek, TheWatchForum | `ReadTimeout` |

**Aucun prix demandé à la revente n'a été obtenu pour les trois références.**

## 3. Catawiki : trois modes de découverte, testés

| Mode | Résultat |
|---|---|
| Recherche interne (12 requêtes, `200`) | lots **ouverts** seulement ; « Aucun résultat exact » à chaque fois ; 208 voisins sémantiques (`isVectorSearchResult`), 42 lots lus, **0 référence exacte** |
| Lot connu, lu par son URL | fonctionne (§1) ; lot **clos** lisible tant que l'URL est connue |
| **Plan du site des lots clos** (nouveau) | `sitemap_closed_index_en.xml` : 47 fichiers, 5 Mo chacun, **2 331 613 lots**, lu en 147 s. **Ni déclaré dans `robots.txt`, ni indexable** (`noindex` dans le nom). Il s'arrête à l'identifiant 106 371 780 (lots clos avant août 2026) : aucun des trois lots ci-dessus n'y figure. Ce qu'il contient : 15 317 lots Omega, 10 243 Cartier, 918 Jaeger. **0 lot portant l'une des trois références exactes.** |

Le plan du site est un vrai moyen de **découverte locale sans moteur de
recherche** (repérer une référence dans l'adresse du lot), mais son retard le
rend aveugle aux lots des dernières semaines, exactement ceux que la recherche
web de ChatGPT a trouvés.

## 4. Découverte par un moteur de recherche utilisable par KAIROS, sans abonnement

| Moyen | Résultat |
|---|---|
| DuckDuckGo (HTML) | `202` + défi anti-robot : arrêté, rien contourné |
| Bing (page de résultats) | répond `200`, mais aucune API gratuite ne l'accompagne et je n'ai pas vérifié ses conditions pour un usage automatisé : non retenu, à ne pas supposer autorisé |
| Google Programmable Search (API JSON) | **fermée aux nouveaux clients**, arrêt annoncé le 1er janvier 2027 ([source](https://developers.google.com/custom-search/v1/overview)) |
| Brave Search API | plus de palier gratuit : 5 $ de crédit mensuel, **carte enregistrée facturée au-delà** ([source](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/)) : c'est un engagement de paiement |
| Wayback Machine (disponibilité) | joignable, mais pour une **URL connue** : aucune capture du lot Omega ; l'index CDX et Common Crawl sont injoignables depuis cet environnement |
| Instance publique SearXNG | joignable, mais gérée par des bénévoles : non interrogée, non fiable pour un logiciel |

**Blocage précis, distinct de l'accès aux pages : il n'existe pas de moteur de
recherche à la fois gratuit, sans carte, autorisé pour un usage automatisé et
joignable.** Les outils web de ChatGPT et de Claude ne sont pas disponibles au
logiciel.

## 5. Restrictions, par nature

| Source | Contractuelle | Technique | Données | Découverte |
|---|---|---|---|---|
| Catawiki | **Conditions générales (en vigueur au 15/09/2026), rubrique « Respect intellectual property » : « Scraping our website is not allowed. We may take any measures available to us under applicable law to prevent or address scraping. »** ([PDF officiel](https://cdn.catawiki.net/assets/marketing/terms/2026/web/general-terms/general-terms-en-092026.pdf?t=497113)) | Akamai : `httpx` `200`, `curl` `403` avec la même identité → accès instable | 0 référence exacte | interne : ouverts seulement ; plan du site : en retard |
| Chrono24 | texte des conditions non lu : la page renvoie le défi | défi Cloudflare sur la recherche **et** sur les conditions | — | — |
| The RealReal | conditions interdisant robots et extraction (rapporté par recherche web ; la page renvoie `403` à mon client) | aucune sur la recherche | noms génériques | — |
| Autres | voir §2 | voir §2 | voir §2 | voir §2 |

L'accès technique n'est pas une permission contractuelle. La décision du
propriétaire autorise KAIROS mais ne peut pas lever les conditions d'un tiers.

## 6. Ce qui est réellement validé aujourd'hui

**Rien de bout en bout.** Un mode est validé s'il réunit : accès réel, aucune
exclusion contractuelle, données exactes, découverte automatique.

| Mode | Accès réel | Contrat | Données exactes | Découverte | Verdict |
|---|---|---|---|---|---|
| Catawiki, lecture de lot par URL | oui (instable) | **exclu** | 3 lots connus | non | non validé |
| Catawiki, lots ouverts | oui | **exclu** | 0 | oui | non validé |
| Catawiki, plan du site des lots clos | oui | **exclu** | 0 | partielle | non validé |
| Chrono24 | non | inconnu | — | — | non validé |
| Boutiques accessibles | partiel | à vérifier une à une | 0 | non | non validé |
| eBay, API officielle (clé développeur gratuite, 5 000 appels/jour) | **non testé** : demande une clé, donc un geste humain unique ; annonces en cours seulement, jamais des ventes | permis par l'API | non testé | oui | à valider |

Conséquence : le parcours autonome n'est pas développé. Le construire
maintenant produirait un moteur vide, ou reposerait sur un mode contractuellement
exclu.

## 7. Défaut trouvé pendant l'essai (POL-094)

Le `User-Agent` du collecteur de production contenait des accents et `httpx`
refuse tout en-tête non ASCII : **le collecteur n'a jamais pu envoyer une
requête réelle**. Aucun test ne le voyait, tous utilisaient un faux collecteur.
Corrigé, avec un test qui construit de vrais en-têtes.

## 8. Décisions à prendre

1. **Catawiki : accepter ou non le risque contractuel.** Cette décision engage
   le propriétaire (suspension de compte, action de Catawiki), pas le code.
   Recommandation : ne pas l'accepter pour un usage automatisé.
2. **Comparables voisins explicites.** Le moteur pondère déjà la similarité. Autoriser,
   pour une référence sans vente exacte, des ventes proches **affichées comme
   voisines** (même famille, même mouvement, même matière) ne serait pas une
   substitution silencieuse, mais donnerait une confiance plafonnée. C'est une
   règle métier : elle relève du jeu de règles, pas du code.
3. **Clé développeur eBay gratuite**, pour tester le seul mode officiel
   restant. Prix demandés et enchères en cours seulement.

## 9. Suite : le mode officiel eBay est implémenté, pas encore prouvé

Le 30 septembre 2026, le propriétaire a engagé la création d'une clé développeur
eBay gratuite. Le parcours autonome est développé **pour ce seul mode validé** :
API Browse officielle, prix demandés et enchères en cours (classe C), jamais des
ventes.

- Réalisé et testé : port de source, adaptateur, contrôle d'identité par
  référence exacte, exclusions de configuration, déduplication, cache et
  fraîcheur, quota, tâche de fond avec résultats par source, provenance, un seul
  recalcul, écran. Parcours navigateur complet contre un **faux serveur eBay**
  sur une vraie prise réseau.
- **Non prouvé** : l'accès réel aux données eBay pour les trois références. Une
  fixture ne le prouve pas. La preuve se fait avec de vrais identifiants :
  `python -m app.market_search.probe` (requêtes réelles, statut HTTP, annonces
  lues, retenues, écartées avec motif, temps total). Vérifié aujourd'hui : le
  jeton OAuth d'eBay est joignable et refuse de faux identifiants avec le
  diagnostic exact (HTTP 401).
- Catawiki et Chrono24 restent **non validés** : aucune lecture automatisée.

## 10. Suite : découverte autonome prouvée sur quatre sources

À la demande du propriétaire (document de passation du 30 septembre 2026), quatre
sources publiques ont été éprouvées **sans liste d'URL** : Phigora (catalogue UCP),
Antiquorum, Sworders, Vintage Watch Agency. Une recherche par marque, modèle et
référence retrouve seule : 3 adjudications Antiquorum et 1 adjudication Sworders
pour la JLC 266.1.44, 1 fiche en stock pour l'Omega 1561.61.00, 2 pour la
Speedmaster 3570.50.00 (référence nouvelle). Aucune fiche exacte pour la Cartier
W1002253. Détail, limites et conditions : `registre-sources.md`.

Catawiki reste **exclu** (clause citée), Chrono24 aussi : aucun contournement.
