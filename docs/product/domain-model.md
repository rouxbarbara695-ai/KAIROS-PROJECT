# Modèle métier

Ce document définit les objets et leurs responsabilités. Il n’est pas une source
de vérité isolée : la hiérarchie complète figure dans `CLAUDE.md`.

## Carte du domaine

- Un `Utilisateur` appartient à un `Portefeuille`.
- Le portefeuille possède un grand livre de trésorerie et des stratégies.
- Une `Opportunité` appartient obligatoirement à un portefeuille.
- Elle provient soit d’une `Annonce`, soit d’une saisie manuelle.
- Une saisie manuelle accumule des `OpportunityPriceInput` append-only.
- Une annonce décrit une `Montre`, un vendeur et une plateforme, et accumule
  des observations immuables.
- La montre peut être rattachée à une `Référence`, confirmée ou inconnue.
- Des `Comparables` alimentent une `Valorisation de marché`.
- Une `Analyse` immuable épingle valorisation, stratégie, ruleset, règles de
  plateforme, coûts, portes, score et verdict.
- Les achats, coûts, mises en vente, ventes et écritures de trésorerie décrivent
  le résultat réel.
- Le `Journal d’audit` trace corrections, exclusions et transitions.

## Responsabilités

| Objet | Responsabilité |
|---|---|
| Portefeuille | périmètre d’accès, capital, stock et performance |
| Opportunité | agrège le contexte d’une décision, sans calculer elle-même |
| Annonce | identité externe, URL canonique et état courant |
| Observation | photographie append-only d’une annonce à un instant |
| Montre | caractéristiques physiques, état, set et statut d’identification |
| Référence | connaissance technique normalisée d’une référence horlogère |
| Comparable | preuve de marché typée, datée, normalisée et éventuellement exclue |
| Valorisation | cote basse/centrale/haute et trace des comparables utilisés |
| Ruleset | jeu immuable de seuils et coefficients |
| Stratégie versionnée | objectifs de profit, ROI, allocation et négociation |
| Règle de plateforme | frais, logistique, conformité et période d’application |
| Analyse | instantané de décision reproductible |
| Événement d’audit | trace append-only d’une mutation autorisée |

## Propriété des données

- L’annonce possède l’URL et l’identifiant externe.
- L’observation possède les valeurs observées, sans réécrire l’annonce passée.
- Le comparable source ne change pas ; une correction crée un événement et une
  nouvelle révision logique.
- La valorisation possède les ajustements et poids utilisés à sa date.
- L’analyse possède les snapshots de règles nécessaires à sa reproduction.
- Le grand livre de trésorerie possède les apports, retraits et mouvements.

## Immuabilité

Une analyse peut être préparée en brouillon. Dès `published_at`, toute mise à
jour ou suppression est interdite. Observations, valorisations, traces de
calcul, événements d’opportunité, événements d’audit et écritures de trésorerie
sont append-only dès leur création.

## Confiances distinctes

| Nom | Sens |
|---|---|
| `identification_confidence` | probabilité que la référence proposée soit correcte |
| `valuation_confidence` | solidité statistique et documentaire de la cote |
| `evidence_quality_score` | pilier du score relatif à la qualité globale des preuves |
| `source_reliability_level` | classe A à E d’un comparable |

Ces valeurs ne sont jamais interchangeables.
