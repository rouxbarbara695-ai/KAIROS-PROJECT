# Contrat API V1

Base `/api/v1`, JSON UTF-8, Bearer hors local. Toute réponse porte
`X-Request-Id`. Tous les timestamps sont ISO 8601 UTC.

## Conventions

### Décimaux

Montants, taux, ROI et scores sont des chaînes décimales JSON :

```json
{
  "amount": "1800.00",
  "currency": "EUR",
  "amount_eur": "1800.00",
  "rate_to_eur": "1.00000000",
  "fx_rate_at": "2026-07-28T10:00:00Z",
  "fx_source": "identity"
}
```

Jamais de nombre flottant JSON pour ces champs.

### Pagination

Ordre par défaut : `created_at DESC, id DESC`. `next_cursor` est un Base64URL
opaque encodant `{"created_at":"...","id":"uuid"}`. Le serveur valide la forme
mais le client ne l’interprète pas. `limit=20`, maximum 100.

### Concurrence

Les réponses modifiables exposent `ETag: "version-n"`. `PATCH` exige
`If-Match`. Un conflit retourne `409 RESOURCE_VERSION_CONFLICT`.

**Ce que couvre la version.** `version` est celle du **dossier**, pas de la
seule ligne `opportunities` : elle bouge dès que change ce que la fiche
présente — état de la montre, vendeur, référence, statut. Sans cela, l’`ETag`
promettrait une fraîcheur que la réponse n’a pas.

**Routes qui exposent l’`ETag`.** Toute réponse portant une opportunité :
`GET /opportunities/{id}`, les trois `PATCH`, `POST
/opportunities/{id}/reference-confirmations`, `POST
/opportunities/{id}/status` et `POST /opportunities`. La création et la
transition l’exposent aussi, faute de quoi la première correction n’aurait
aucune version à citer.

**Routes qui exigent `If-Match`.** Les trois corrections :
`PATCH /opportunities/{id}`, `PATCH /opportunities/{id}/watch-profile`,
`PATCH /opportunities/{id}/seller-profile`.

**Forme acceptée.** `"version-<entier>"`, guillemets compris, éventuellement
préfixée `W/`. Toute autre forme retourne `422 VALIDATION_ERROR`. `*` est
refusé : « n’importe quelle version » est exactement l’écrasement aveugle que
la protection remplace. L’en-tête absent retourne
`409 RESOURCE_VERSION_CONFLICT` avec `details.reason = "if_match_required"` —
une correction qui ne dit pas ce qu’elle a lu n’est pas acceptée par défaut.

**Vérification atomique.** La comparaison de version faite en amont sert à
rendre l’erreur immédiate et à ne pas engager de travail inutile ; elle ne
constitue pas la garantie. Chaque `UPDATE` d’opportunité porte
`where version = <valeur lue>` : si une transaction concurrente a écrit
entre-temps, aucune ligne ne correspond et la requête est refusée. Le conflit
constaté à l’écriture porte `details.reason = "concurrent_write"` ; celui
constaté en amont porte `details.expected_version` et
`details.current_version`.

**Côté client.** Un conflit **conserve la saisie** et propose de recharger.
Renvoyer d’office avec la nouvelle version écraserait le travail de l’autre
onglet — précisément ce que la protection existe pour empêcher.

### Idempotence

`POST` de création, transitions et écritures financières acceptent
`Idempotency-Key` (1–128 caractères). Même clé + même empreinte retourne la
réponse initiale ; même clé + charge différente retourne
`409 IDEMPOTENCY_CONFLICT`.

**Routes concernées.** L’en-tête est déclaré dans l’OpenAPI des routes
suivantes ; partout ailleurs il est ignoré.

| Route | Effet protégé |
|---|---|
| `POST /opportunities` | ouverture d’un dossier |
| `POST /opportunities/{id}/status` | transition de statut |
| `POST /opportunities/{id}/purchase` | achat + sortie de trésorerie |
| `POST /opportunities/{id}/sale-listing` | mise en vente |
| `POST /opportunities/{id}/sale` | vente |
| `POST /opportunities/{id}/payout` | encaissement + entrée de trésorerie |
| `POST /portfolios/{id}/ledger-entries` | mouvement de trésorerie |

**Portée.** La clé est unique par `(portefeuille, clé)`. Le portefeuille est
celui de la ressource visée — déduit de l’opportunité pour les routes qui la
nomment, du chemin ou du corps pour les autres. Deux portefeuilles peuvent donc
employer la même chaîne sans se gêner, et une clé ne peut jamais rejouer la
réponse d’un portefeuille voisin. La méthode et le chemin font partie de
l’empreinte comparée : réemployer une clé sur une autre route est un conflit,
pas un rejeu.

**Empreinte.** SHA-256 des octets bruts du corps reçu, pas d’un objet
ré-encodé : deux sérialisations du même contenu peuvent différer par l’ordre
des clés, et l’empreinte doit refuser exactement ce que l’appelant a refusé
d’envoyer deux fois.

**Conservation.** Vingt-quatre heures. Au-delà, la clé redevient libre. Un
renvoi honnête suit l’original de quelques secondes ; ce délai couvre
l’utilisateur qui reprend le lendemain matin après une coupure, sans condamner
indéfiniment une chaîne qu’une opération légitime réemploierait plus tard.

**Requêtes simultanées.** La place est prise par un `insert … on conflict do
nothing` : c’est l’index unique qui désigne le gagnant, jamais une lecture
préalable. Tant que la première requête n’a pas répondu, les suivantes
reçoivent `409 IDEMPOTENCY_CONFLICT` avec `details.reason = "in_progress"` ; un
conflit de charge porte `details.reason = "payload_mismatch"` et rappelle la
méthode et le chemin d’origine.

**Échec.** Une opération qui lève **libère** sa clé : rien n’a été écrit, et
l’appelant doit pouvoir réessayer avec la même chaîne. Une réservation restée
sans réponse plus de cinq minutes est tenue pour abandonnée et récupérée, faute
de quoi un processus interrompu condamnerait la clé pour vingt-quatre heures.

**Côté client.** Une nouvelle action reçoit une clé neuve ; tous ses renvois
gardent la même tant qu’elle n’a pas abouti. La clé n’est oubliée qu’au succès
— c’est après un échec que l’utilisateur réappuie, et c’est le seul moment où
l’issue de l’appel précédent est inconnue.

### Préremplissage depuis un lien

`POST /listings/prefill` récupère **une** annonce, à la demande explicite de
l’utilisateur. Aucune surveillance périodique, aucune collecte de masse : la
validation d’accès est étroite et datée (`docs/decisions/open-questions.md`,
Q-04/05/06).

**Ces routes n’écrivent rien.** Elles rendent un brouillon ; c’est
`POST /opportunities` qui crée. Un préremplissage abandonné ne laisse aucune
trace, et recoller un lien ne provoque pas un conflit de doublon.

**Un refus est un résultat, pas une erreur.** La route rend `200` avec
`succeeded: false`, le lien conservé, le motif précis et le repli à proposer :

| `access_mode` | Ce que fait KAIROS |
|---|---|
| `automatic` | récupère la page |
| `assisted` | n’émet aucune requête ; propose l’import assisté |
| `forbidden` | n’émet aucune requête ; les conditions de la plateforme l’interdisent |

`GET /listings/access` rend ce mode **avant** toute tentative, pour que
l’interface annonce le repli au moment où le lien est collé.

**Chaque champ est un objet**, jamais une valeur nue :

```json
{
  "raw": "GBP 7,995",
  "value": "7995",
  "provenance": "imported",
  "source": "schema.org/Offer.price",
  "conflicts": []
}
```

`provenance` vaut `imported` (page récupérée par le serveur), `assisted`
(contenu fourni par l’utilisateur), `user` (corrigé à la main) ou `absent`.
**`absent` n’est pas une valeur vide : c’est un constat.** Un champ que
l’annonce ne donne pas reste `absent` et ne reçoit jamais de défaut favorable.
Aplatir cette structure ferait perdre exactement ce qui rend le préremplissage
sûr : la distinction entre une valeur lue et une valeur supposée.

**Ce qui n’est jamais déduit** : l’année, la référence, le diamètre et le
calibre absents de la page restent absents ; « full set » ne remplit ni la
boîte ni les papiers, qui se lisent séparément ; « occasion » ne produit aucune
note cosmétique ; un montant sans devise n’est pas repris ;
« authenticité garantie » reste une déclaration du vendeur. Chacun de ces cas
produit un `warning` en clair plutôt qu’une valeur.

**Numéros de série** : retirés de tout texte importé (règle 11). La réponse dit
qu’il y en avait un, jamais lequel.

**Catawiki : import assisté obligatoire.** Catawiki refuse toute requête
serveur (`403` Akamai sur tous ses domaines, jusque sur `robots.txt`) et n’offre
pas d’API publique côté acheteur. C’est pourtant la plateforme d’achat
principale, donc l’import assisté y est le parcours normal et non un repli.
L’utilisateur colle le **texte visible** de la page (`Ctrl+A`, `Ctrl+C`) ; ni
code source ni outils de développement ne sont demandés. L’extraction y est
pilotée par les étiquettes — français, anglais, néerlandais — et non par la
position des lignes.

**Champs propres aux enchères.** `lot_number`, `current_bid_amount`,
`current_bid_currency`, `bid_count`, `closing_at`, `closing_timezone`,
`estimate_low`, `estimate_high`, `estimate_currency`, `reserve_status`
(`no_reserve` / `not_met` / `met`), `shipping_cost_amount`,
`shipping_cost_currency`, `shipping_destination`, `seller_since`.

Trois règles y gouvernent la lecture :

- **une enchère en cours est une enchère.** Elle part en `price.kind =
  "current_bid"`, jamais `asking` : elle montera, et elle peut ne pas atteindre
  la réserve ;
- **l’estimation de la plateforme n’est pas celle de KAIROS.** Elle occupe ses
  propres champs et n’entre dans aucun calcul ;
- **l’horodatage du relevé accompagne le montant.** Un prix d’enchère sans
  l’heure à laquelle il a été lu ne veut rien dire.

**Trace de l’import.** `POST /opportunities` accepte un `import_draft`
facultatif : les champs tels que le préremplissage les a rendus, avec leur
provenance. Il est écrit dans une observation d’annonce — **append-only** — et
relu par `GET /opportunities/{id}/import`. C’est ce qui permet, en rouvrant un
dossier des semaines plus tard, de distinguer ce qui venait de l’annonce de ce
qui a été corrigé à la main. Un second import ajoute une observation ; il
n’écrase pas la précédente.

**Garde-fous de la récupération** : `https` seul, domaines autorisés par
plateforme, adresses résolues vérifiées comme publiques, redirections
revalidées une à une (trois au plus), délai de 10 s, corps borné à 2 Mio. Le
contenu distant est traité comme une donnée : il n’est ni exécuté, ni obéi, et
il est nettoyé avant d’être stocké ou affiché.

### Limitation de débit

`POST /auth/login` est la seule route publique de l’API. Les échecs y sont
comptés par adresse IP d’origine et par adresse électronique, sur une fenêtre
glissante de cinq minutes. Au-delà du seuil, la route retourne
`429 RATE_LIMITED` avec `details.retry_after_seconds`, **avant** toute
vérification de mot de passe : Argon2 est lent par construction, et laisser un
attaquant déclencher ce calcul lui offrirait le déni de service que la
limitation doit empêcher.

Le seuil par adresse électronique est délibérément beaucoup plus haut que celui
par adresse IP. KAIROS est mono-organisation : une limite serrée par adresse
donnerait à n’importe qui le moyen d’enfermer le propriétaire dehors en
martelant la sienne.

Une connexion réussie remet les compteurs à zéro. Si le compteur est
injoignable, la connexion reste possible et l’incident est journalisé : la
frontière de sécurité est le mot de passe, pas le limiteur.

## Ressources

| Méthode | Route | Fonction |
|---|---|---|
| POST | `/opportunities` | créer en mode manuel ou URL |
| GET | `/opportunities` | lister/filtrer |
| GET | `/opportunities/{id}` | détail et dernière analyse |
| PATCH | `/opportunities/{id}` | corriger les champs autorisés avec motif |
| POST | `/opportunities/{id}/reference-confirmations` | confirmer/corriger/inconnue |
| PATCH | `/opportunities/{id}/watch-profile` | corriger état/set avec audit |
| PATCH | `/opportunities/{id}/seller-profile` | corriger vendeur/pays avec audit |
| POST | `/opportunities/{id}/price-inputs` | ajouter prix manuel/enchère daté |
| GET | `/opportunities/{id}/events` | historique métier et audit |
| POST | `/opportunities/{id}/observations` | observation manuelle |
| POST | `/listings/prefill` | préremplir depuis un lien, à la demande |
| POST | `/listings/prefill/assisted` | préremplir depuis un contenu fourni |
| GET | `/listings/access` | mode d’accès applicable à un lien |
| GET | `/opportunities/{id}/import` | ce que l’annonce affichait à l’import |
| POST | `/opportunities/{id}/comparables` | ajouter comparable |
| POST | `/comparables/{id}/overrides` | corriger/exclure/réintégrer avec motif |
| POST | `/opportunities/{id}/analyses` | créer/recalculer |
| GET | `/opportunities/{id}/analyses` | historique immuable |
| GET | `/analyses/{id}` | détail et traces |
| POST | `/opportunities/{id}/transitions` | changer le pipeline |
| POST | `/opportunities/{id}/costs` | coût prévu/réel |
| POST | `/opportunities/{id}/purchases` | enregistrer achat |
| POST | `/opportunities/{id}/sale-listings` | mise en vente |
| POST | `/opportunities/{id}/sales` | vente |
| POST | `/portfolio/ledger-entries` | apport/retrait/mouvement |
| GET | `/portfolio/summary` | cash, encours, stock, performance |
| GET/POST | `/strategies` | stratégies et versions |
| GET | `/rulesets/{version}` | ruleset immuable |
| GET | `/platforms/{code}/rules` | règle applicable à date/région |
| GET | `/alerts` | alertes |
| PATCH | `/alerts/{id}` | marquer lue/archivée |
| GET | `/jobs/{id}` | état d’un job autorisé |

## Création manuelle

```json
{
  "portfolio_id": "uuid",
  "source": {
    "mode": "manual",
    "manual_identifier": "LONGINES-2026-001"
  },
  "watch": {
    "brand": "Longines",
    "reference": "L2.257.4.57.6",
    "reference_status": "unconfirmed",
    "mechanical_condition": "functional",
    "cosmetic_condition": "like_new",
    "box": true,
    "papers": true
  },
  "seller": {
    "country_code": "FR",
    "seller_type": "private"
  },
  "price": {
    "amount": "1800.00",
    "currency": "EUR"
  }
}
```

Retour synchrone `201` avec `id`, `source.mode=manual`, `status=watching`,
`version=1`. Il n’existe pas d’`import_status` pour le mode manuel.

Création URL : `source.mode=url`, `url`. Retour `201` si seule l’URL est stockée
pour saisie manuelle ; `202` avec `job_id` seulement si un import autorisé est
effectivement lancé.

Doublons : `409 OPPORTUNITY_DUPLICATE` avec `existing_opportunity_id` et
`matched_on=canonical_url|external_id|manual_identifier`.

## Correction

`PATCH /opportunities/{id}` autorise uniquement : statut courant non financier,
stratégie sélectionnée et données de présentation. Référence, montre, vendeur,
prix, état, set et données financières utilisent leurs commandes dédiées. Toute
correction exige `reason`.

Les corrections `watch-profile` et `seller-profile` modifient la projection
courante, conservent le brut d’origine et écrivent obligatoirement un
`audit_event` avec `before_data`, `after_data`, auteur et motif dans la même
transaction.

## Confirmation de référence

```json
{
  "status": "corrected",
  "reference_id": "uuid",
  "reason": "Référence visible sur les papiers"
}
```

Statuts : `suggested|confirmed|corrected|unknown`. Une nouvelle confirmation ne
réécrit pas l’événement précédent.

## Analyse complète

```json
{
  "analysis_id": "uuid",
  "previous_analysis_id": null,
  "ruleset_version": "1.0.0",
  "strategy_version_id": "uuid",
  "platform_rule_id": "uuid",
  "calculated_at": "2026-07-28T12:00:00Z",
  "published_at": "2026-07-28T12:00:01Z",
  "current_price_eur": "1200.00",
  "gates": [
    {"code": "G1_AUTHENTICITY", "status": "passed", "reason_codes": []},
    {"code": "G2_IDENTIFICATION", "status": "passed", "reason_codes": []},
    {"code": "G3_DATA_QUALITY", "status": "passed", "reason_codes": []},
    {"code": "G4_MARKET_SUPPORT", "status": "passed", "reason_codes": []},
    {"code": "G5_SELLER_RISK", "status": "passed", "reason_codes": []}
  ],
  "valuation": {
    "low_eur": "1650.00",
    "central_eur": "1800.00",
    "high_eur": "1950.00",
    "valuation_confidence": "72.00"
  },
  "scenarios": {
    "prudent": {
      "sale_price_eur": "1650.00",
      "total_cost_eur": "1290.00",
      "net_sale_proceeds_eur": "1570.00",
      "profit_eur": "280.00",
      "roi": "0.21705426"
    },
    "central": {
      "sale_price_eur": "1800.00",
      "total_cost_eur": "1275.00",
      "net_sale_proceeds_eur": "1710.00",
      "profit_eur": "435.00",
      "roi": "0.34117647"
    },
    "favorable": {
      "sale_price_eur": "1950.00",
      "total_cost_eur": "1260.00",
      "net_sale_proceeds_eur": "1850.00",
      "profit_eur": "590.00",
      "roi": "0.46825397"
    }
  },
  "pricing": {
    "raw_max_purchase_price_eur": "1334.72",
    "max_purchase_price_eur": "1330.00",
    "binding_constraint": "minimum_profit",
    "expected_sale_price_eur": "1800.00",
    "expected_profit_eur": "435.00",
    "expected_roi": "0.34117647",
    "expected_days_to_sell": 45
  },
  "score": {
    "raw_total": "78.5000",
    "total": "78.50",
    "pillars": {
      "profitability": "82.00",
      "liquidity": "70.00",
      "portfolio": "76.00",
      "condition": "90.00",
      "evidence_quality": "68.00"
    },
    "caps": []
  },
  "recommendation": "buy",
  "decision_reasons": [
    {
      "code": "PRICE_BELOW_MAXIMUM",
      "message": "Le prix courant est inférieur de 130,00 € au maximum prudent.",
      "impact_eur": "130.00"
    }
  ]
}
```

Les nombres de cet exemple illustrent la **forme du contrat**, pas une fixture
arithmétique. Les fixtures faisant foi sont dans la stratégie de tests.

## Analyse impossible

Une réponse publiée peut contenir `recommendation=analysis_impossible`,
`valuation=null`, `scenarios=null`, `pricing=null`, `score=null`, avec les portes
et raisons d’échec. Elle est persistée comme toute autre analyse.

## Erreurs

| Code | HTTP | Usage |
|---|---:|---|
| `VALIDATION_ERROR` | 422 | champ invalide |
| `UNAUTHORIZED` / `FORBIDDEN` | 401 / 403 | accès |
| `NOT_FOUND` | 404 | ressource absente dans le portefeuille |
| `OPPORTUNITY_DUPLICATE` | 409 | clé déjà suivie |
| `IDEMPOTENCY_CONFLICT` | 409 | même clé, autre charge |
| `RESOURCE_VERSION_CONFLICT` | 409 | `If-Match` obsolète |
| `IMMUTABLE_RESOURCE` | 409 | modification d’un historique |
| `INVALID_TRANSITION` | 409 | pipeline interdit |
| `REFERENCE_UNCONFIRMED` | 422 | analyse non autorisée |
| `GATE_FAILED` | 422 | commande exigeant portes passées |
| `VALUATION_INSUFFICIENT_COMPARABLES` | 422 | moins de 2 |
| `FX_RATE_UNAVAILABLE` | 503 | taux absent/expiré |
| `COLLECTOR_NOT_AUTHORIZED` | 403 | mode d’accès non validé |
| `COLLECTOR_UNAVAILABLE` | 503 | échec externe |
| `RATE_LIMITED` | 429 | trop de tentatives |
| `RULESET_MISSING` | 500 | version non résolue |
| `INTERNAL_ERROR` | 500 | échec d’écriture non traduit |

Format :

```json
{
  "error": {
    "code": "RESOURCE_VERSION_CONFLICT",
    "message": "La ressource a été modifiée.",
    "field": null,
    "details": {"current_version": 3},
    "request_id": "uuid"
  }
}
```

## Jobs

`GET /jobs/{id}` retourne
`queued|running|succeeded|failed|partial`, tentatives et erreurs par source. Une
relance conserve la clé d’idempotence ; chaque succès partiel est conservé.
