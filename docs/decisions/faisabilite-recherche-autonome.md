# Faisabilité de la recherche autonome de comparables — constat du 30 septembre 2026

**Statut : la fonctionnalité n'est PAS livrée.** Ce document est le constat
demandé par la décision « Correction de périmètre » : l'essai réel a été mené
avant toute infrastructure, et il ne réussit pas sur les sources nécessaires.

## Ce qui a été fait

Un essai **réel** (pas une fixture) sur les trois références, avec le client
HTTP de production de KAIROS : agent honnête, `robots.txt` respecté, deux
secondes entre deux requêtes d'un même domaine, aucune nouvelle tentative après
un blocage, aucun contournement de défi.

- Sonde multi-sources : 13 sources, 39 sondages, **33,7 s**.
- Recherche Catawiki lot par lot : 12 recherches, 3 × 14 pages de lot lues,
  **152,4 s**.
- Interventions humaines nécessaires : **aucune** pour ces essais.

## Résultat par source

| Source | Nature attendue | Résultat réel | Diagnostic exact |
|---|---|---|---|
| Chrono24 | prix demandé (revente) | **Bloquée** | `403`, `cf-mitigated: challenge` (défi Cloudflare). Source arrêtée, rien contourné. |
| Catawiki | enchère en cours / marteau | **Accessible, 0 comparable exact** | Recherche et pages de lot en `200`. Voir ci-dessous. |
| Watchfinder | prix demandé | Bloquée | `robots.txt` en `403` (CloudFront) : aucune recherche émise. |
| Bonhams, Interenchères | résultats de vente | Bloquées | `robots.txt` en `403` (Cloudflare). |
| Vestiaire Collective, LiveAuctioneers, Phillips | — | Non interrogées | `robots.txt` interdit le chemin de recherche. |
| Christie's, Bucherer | — | Inexploitables | `200` mais coquille JavaScript : aucune donnée dans le HTML. |
| The RealReal | prix demandé | Accessible, inexploitable | `200`, produits présents mais à noms génériques : la référence ne se prouve pas sans page produit ; ses conditions interdisent les robots. |
| Drouot | résultats de vente | Inexploitable | `404` : le gabarit d'URL de recherche est inconnu. |
| 1stDibs | prix demandé | Échec | `ReadTimeout`, source arrêtée. |
| eBay | — | Non interrogée | Interdit par la table d'accès (`FORBIDDEN`). |

### Catawiki, en détail

| Référence | Recherches | Lots en cours vus | Lots lus | **Référence exacte trouvée** |
|---|---|---|---|---|
| JLC Reverso Duetto 266.1.44 | 4 (`200`) | 71 | 14 | **0** |
| Cartier Vendôme W1002253 | 4 (`200`) | 70 | 14 | **0** |
| Omega Constellation 1561.61.00 | 4 (`200`) | 67 | 14 | **0** |

- Chaque recherche affiche « Aucun résultat exact » : les lots renvoyés sont des
  **voisins sémantiques** (`isVectorSearchResult`), pas la référence demandée.
  Les substituer serait exactement le remplacement silencieux interdit.
- Le moteur de recherche de Catawiki ne renvoie **que les lots ouverts**. Une
  enchère en cours (`current_bid`) n'est de toute façon pas un prix réalisé.
- Les trois lots **clôturés** connus (collés le 8 septembre) sont lisibles par
  leur URL — Cartier 1 200 € au marteau, Omega 800 € au marteau, JLC réserve
  **non atteinte** (donc **pas une vente**, et l'URL redirige vers un lot
  republié) — mais **rien ne permet de les découvrir** sans connaître l'URL.
- Total : **0 comparable exploitable** sur les 3 références.

## Trois obstacles

1. **Découverte des ventes clôturées.** C'est ce dont l'estimation a besoin
   (prix réalisés, classes A/B). Aucune source accessible ne les liste. Les
   archives publiques (Wayback CDX, Common Crawl) sont injoignables depuis le
   bac à sable ; un moteur de recherche à clé gratuite (Google Programmable
   Search, Brave) exige de créer une clé : geste humain, et un extrait de
   résultat ne prouve ni un prix ni une vente.
2. **Côté revente, Chrono24 est bloquée** par un défi anti-robot. La consigne
   interdit de le contourner. Sans elle, il n'y a aucun prix demandé de revente.
3. **Conditions d'utilisation.** Les conditions générales de Catawiki (en
   vigueur au 15 septembre 2026) déclarent que l'extraction automatisée n'est
   pas autorisée et que Catawiki peut prendre des mesures ; celles de The RealReal
   interdisent robots et extraction sans accord écrit. L'accès technique n'est
   pas une permission contractuelle. La décision de l'utilisateur autorise
   KAIROS ; elle ne peut pas modifier les conditions d'un tiers. À trancher
   par une personne qui peut engager l'organisation, pas par le code.

## Fragilité constatée

Avec le même agent honnête, `httpx` reçoit `200` de Catawiki et `curl` reçoit
`403` : Akamai décide selon l'empreinte de la connexion. L'accès n'est donc ni
garanti ni stable. Non testé : l'adresse du serveur OVH peut être traitée
autrement que celle du bac à sable.

## Défaut trouvé pendant l'essai (POL-094)

Le `User-Agent` du collecteur de production contenait des lettres accentuées.
`httpx` refuse tout en-tête non ASCII (`UnicodeEncodeError`) : **le collecteur
de production n'a jamais pu envoyer une seule requête**. Tous ses tests
utilisaient un faux collecteur, d'où un défaut invisible. Corrigé (ASCII) et
couvert par un test qui utilise la vraie bibliothèque.

## Possibilités restantes (aucune n'est engagée)

1. **Accord ou canal officiel.** Demander à Catawiki et à Chrono24 un accès
   autorisé (API partenaire, export). Seule voie durable pour les deux sources
   nécessaires. Décision et démarche humaines.
2. **Découverte par moteur à clé gratuite**, pour retrouver des URL de lots
   clôturés, puis lecture de chaque page publique. Geste humain unique (créer
   la clé), quota limité, et le point 3 ci-dessus reste entier.
3. **Boutiques publiques accessibles** (à inventorier une par une avec la même
   méthode) pour des prix demandés — utile mais insuffisant seul : ce sont des
   prix d'offre (classe C), jamais des prix réalisés.
4. **Recherche limitée à ce qui est accessible et permis** : lots Catawiki en
   cours dont la référence exacte apparaît, affichés comme enchères en cours,
   sans estimation si les données sont insuffisantes. Honnête, mais n'atteint
   pas l'objectif « estimation de prix réalisé ».

L'architecture de la recherche autonome (port de source, adaptateur par site,
déduplication, cache, limites, arrêt sur blocage, tâche de fond avec progression
et erreurs par source) est réalisable, mais la bâtir avant de disposer d'une
source qui livre des comparables exacts produirait un moteur vide. Elle n'est
pas engagée tant que les points 1 à 3 ne sont pas tranchés.
