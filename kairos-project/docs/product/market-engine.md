# Market Engine

Le Market Engine construit une estimation défendable à partir de comparables
normalisés.

## Règles essentielles

- même référence en priorité ;
- état et set comparables ;
- vendeurs distincts afin d’éviter les doublons ;
- distinction stricte entre prix demandé et prix réalisé ;
- frais et devise normalisés ;
- pondération selon récence, qualité, source et proximité du comparable ;
- signalement des anomalies de prix plutôt que suppression silencieuse ;
- marché principal adapté à la marque, au segment et au niveau de prix.

## Sortie

Chaque `MarketValuation` contient :

- valeur basse, centrale et haute ;
- date de calcul ;
- comparables et poids utilisés ;
- niveau de confiance ;
- tendance ;
- explication des exclusions ;
- version des règles de calcul.
