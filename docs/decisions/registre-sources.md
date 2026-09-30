# Registre des sources de comparables — 30 septembre 2026

Une source n'est pas « autorisée » parce que sa page répond `200` ou que son
`robots.txt` laisse passer un chemin. Ce registre garde, par source : le mode
d'accès, les conditions lues (page, date, contenu), la preuve d'accès **réelle**,
la nature des prix, le rythme — et **ce qui n'a pas pu être vérifié**. Son
pendant exécutable est `apps/api/app/market_search/domain/source_registry.py`.

Toutes les sondes ont été faites avec le client de production de KAIROS (agent
honnête, `robots.txt` lu, rythme de la source, aucun contournement). Preuves :
`python -m app.market_search.probe` ; pages réelles rejouées dans
`apps/api/tests/fixtures/sources/`.

## Sources activées (à la demande, jamais en continu)

| Source | Statut | Mode | Nature du prix | Conditions lues |
|---|---|---|---|---|
| eBay | validé | API officielle Browse | prix demandés, enchères en cours | contrat de licence de l'API (30/09/2026) |
| Phigora | **conditionnel** | catalogue UCP publié par la boutique | prix demandés ; « Sold » = dernier prix affiché | **non lues** : page protégée par un défi anti-robot (HTTP 429) |
| Antiquorum | **conditionnel** | pages publiques `/en/lots` | adjudications publiées, frais acheteur inconnus | conditions de vente (Genève) : aucune clause sur l'accès automatisé ; conditions d'utilisation du site non localisées |
| Sworders | **conditionnel** | pages publiques `/auction/search` | adjudications publiées, frais acheteur inconnus | conditions de vente : aucune clause sur l'accès automatisé ; `crawl-delay` 10 s |
| Vintage Watch Agency | **conditionnel** | pages publiques `/search-results.html` | prix demandés d'un marchand | page « Terms of Use » **sans texte** pour un client sans navigateur : non lues |

« Conditionnel » : accès réel prouvé, aucune exclusion trouvée, mais une part des
conditions n'a pas pu être lue. **Le propriétaire peut désactiver une source** en
retirant son nom de `MARKET_SEARCH_SOURCES`.

## Sources exclues

| Source | Motif | Nature |
|---|---|---|
| Catawiki | « Scraping our website is not allowed. We may take any measures available to us under applicable law to prevent or address scraping. » (conditions générales en vigueur au 15/09/2026, « Respect intellectual property ») | contractuelle |
| Chrono24 | défi anti-robot sur la recherche et sur les conditions ; articles 6.2 et 6.3 des conditions restreignant la recherche automatisée (rapporté, non relu) | technique + contractuelle |
| The RealReal, Vestiaire, LiveAuctioneers, Phillips, Watchfinder, Bonhams, Interenchères… | voir `faisabilite-recherche-autonome.md` | technique ou `robots.txt` |

## Preuves réelles par référence (recherche autonome, sans liste d'URL fournie)

| Référence (modèle saisi) | Antiquorum | Sworders | Vintage Watch Agency | Phigora |
|---|---|---|---|---|
| JLC 266.1.44 (Reverso Duetto) | **3 adjudications** : 75 000 HKD (2025-05-31), 7 750 CHF (2013-05-12), 15 600 USD (2009-12-09) | **1** : 3 500 £ (2025-11-18) | 0 | 31 lues, 0 exacte |
| Cartier W1002253 (Must de Cartier Vendome) | 3 lues, 0 exacte | 0 | 0 | 6 lues, 0 exacte |
| Omega 1561.61.00 (Constellation) | 47 lues sur 580, 0 exacte, **lecture partielle** | 8 fiches sur 42, 0 exacte, **lecture partielle** | **1** : 1 520 € (en stock) | 1 exacte, **vendue**, dernier prix 1 699 $ non daté : montrée, hors estimation |
| Omega 3570.50.00 (Speedmaster), référence nouvelle | 49 lues, 0 exacte, partielle | 7 fiches, 0 exacte | **2** : 4 500 € et 5 250 € (en stock) | 6 exactes **vendues**, prix non datés : montrées, hors estimation |

Temps totaux : 24 s, 12 s, 103 s, 91 s. Interventions humaines : aucune. Les
montants en devises sont convertis avec les taux de la BCE, à titre **indicatif** :
le montant d'origine, sa devise et sa date sont toujours conservés.

## Ce que ces résultats ne disent pas

- Les lots de JLC sont des **Reverso Duetto Joaillerie** (or et diamants) ; celui de
  Sworders est sur cuir. Même référence, configurations différentes : KAIROS
  **relève** la configuration (métal, bracelet, mouvement) et l'affiche, sans
  exclure ni pondérer. La règle de comparabilité est une décision métier.
- Une adjudication publiée n'est **pas une preuve de paiement** : classe B, jamais A.
  Les sites ne disent pas si la commission acheteur est comprise : `fees_status =
  unknown`, jamais normalisé en silence.
- Un marchand qui affiche encore un article « vendu » donne un **ancien prix
  demandé**, pas un prix de vente, et sans date : il est montré et laissé hors de
  l'estimation.
- **Cartier W1002253** : aucune source n'en a une fiche exacte aujourd'hui. Les
  lots Catawiki et l'annonce Chrono24 cités par le dossier ChatGPT restent hors
  périmètre (sources exclues). Sans donnée, KAIROS le dit et ne fabrique aucune cote.
- Couverture **partielle** : sans modèle saisi, ou avec un modèle très répandu
  (« Constellation » : 580 lots), les maisons de ventes ne sont lues que
  partiellement (pages et fiches plafonnées par `SearchPolicy`). L'absence d'une
  fiche n'est alors pas une preuve, et l'écran le dit.
- **Profil d'agent UCP** : KAIROS déclare son propre profil (lecture de catalogue
  seulement), servi aujourd'hui par jsDelivr depuis ce dépôt public. À remplacer par
  le domaine de production quand il le servira.
