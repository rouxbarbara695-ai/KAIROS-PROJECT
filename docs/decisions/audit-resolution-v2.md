# Résolution des audits V2

Ce document enregistre les arbitrages adoptés. Ils sont implémentables,
versionnés et réversibles par nouvelles versions, pas par réécriture.

## Arbitrages structurants

| Sujet | Décision V2 |
|---|---|
| Produit évalué | KAIROS évalue l’opportunité en estimant notamment la montre |
| MVP | parcours manuel complet ; automatisation conditionnelle |
| Marque | graphie `KAIROS`; « anticiper » = scénarios, pas découverte |
| Progression | capitalisation humaine prévision/réalisé, sans ML |
| Domaine | V1 spécifique aux montres et mono-organisation |
| Documentation | français, index complet, hiérarchie dans `CLAUDE.md` |
| Prix marché | coût total payé par l’acheteur |
| Maximum | scénario prudent et formules algébriquement corrigées |
| Confiances | quatre noms distincts, jamais `confidence` seul |
| Historique | contenu des règles, stratégies, valorisations, analyses et audit immuable ; seule la clôture `valid_to` d’une règle de plateforme est permise |

## Audit de conception A–N

| Point | Résolution |
|---|---|
| A documents fantômes | tous indexés dans README, PRD README et ordre Claude |
| B langue | tous les documents actifs sont en français |
| C objet évalué | formulation unique dans vision, valeur, PRD et score |
| D signature | sens d’« anticiper » défini dans `brand.md` |
| E apprentissage | remplacé par capitalisation et revue humaine |
| F autres marchés | ambition future, architecture V1 horlogère |
| G SaaS | étape future exigeant un cadrage multi-tenant |
| H suivi automatique | retiré du MVP manuel, KAI-405 conditionnel |
| I scraping | tout accès automatisé exige validation écrite |
| J casse | `KAIROS` partout |
| K métriques | KPI produit séparés des non-régressions et télémétrie ajoutée |
| L roadmap | correspondance explicite avec Epics/stories |
| M confiance narrative | quatre notions nommées dans le modèle |
| N source unique | hiérarchie multi-documents, plus d’auto-proclamation |

## Contradictions C-01 à C-11

| Point | Résolution |
|---|---|
| C-01 portes | cinq codes longs stables, définis une seule fois |
| C-02 confiance | identification, valorisation, preuve, fiabilité A–E |
| C-03 double source | six facteurs ; fiabilité de source une seule fois |
| C-04 prix net | `buyer_total_price_eur`; aucun frais vendeur retranché |
| C-05 maximum | formules corrigées dans §6 calculs |
| C-06 scénario | maximum et verdict prudents ; affichage attendu central |
| C-07 état | 40/35/20/5, total 100 % |
| C-08 dépendances | onze règles quantifiées et ordonnées |
| C-09 sprint | Sprint 1 limité à KAI-001–003 et KAI-101–103 |
| C-10 exemple API | prix courant/base explicites ; exemple non oracle |
| C-11 stratégie | pas de JSON concurrent ; analyse épingle version + snapshot |

## Écarts de schéma S-01 à S-16

| Point | Résolution dans `schema.sql` |
|---|---|
| S-01 FX | montants source/EUR, taux, source/date et FK quand non-EUR |
| S-02 analyse impossible | valorisation et finances nullables |
| S-03 immuabilité | triggers update/delete et `published_at` |
| S-04 manuel | listing nullable, identifiant manuel et prix manuel append-only |
| S-05 confirmation | statut, auteur et date sur la montre + événements |
| S-06 audit | `audit_events` append-only |
| S-07 plateformes | contrat structuré complet + exclusion de chevauchement |
| S-08 incertitude coûts | low/central/high, phase, fixed/rate et assiette |
| S-09 capital | grand livre `portfolio_ledger_entries` |
| S-10 traces comparables | snapshots et facteurs Decimal dans jointure |
| S-11 rulesets | table immuable + snapshot et version épinglés |
| S-12 délai | `listed_at`, `ended_at`, `market_status` |
| S-13 portefeuille | `portfolio_id NOT NULL` sur ressources utilisateur |
| S-14 idempotence/alertes | tables et index uniques |
| S-15 enchères | prix typés et champs réserve/fin |
| S-16 mineurs | collecte id, updated trigger, serial chiffré, interdiction estimation KAIROS, seeds, chaîne linéaire |

## API A-01 à A-09

| Point | Résolution |
|---|---|
| A-01 import_status | supprimé du manuel ; job seulement si import lancé |
| A-02 confirmation | endpoint dédié |
| A-03 PATCH ambigu | champs limités ; commandes dédiées et motif |
| A-04 historique | endpoint événements |
| A-05 stratégies | endpoints stratégie/ruleset |
| A-06 jobs | route dans la table |
| A-07 erreurs | idempotence, concurrence, immuabilité ajoutées |
| A-08 curseur | ordre et Base64URL définis |
| A-09 décimaux | chaînes JSON obligatoires |

## Règle de changement

Une évolution V3 doit mettre à jour ce registre, les sources de vérité
concernées, les fixtures et la version de ruleset si le résultat calculé change.
