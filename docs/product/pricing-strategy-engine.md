# Moteur de pricing

Le moteur transforme la cote de marché en trois scénarios d’opération.

| Scénario | Prix de vente | Coûts incertains |
|---|---|---|
| prudent | cote basse | borne haute |
| central | cote centrale | borne centrale |
| favorable | cote haute | borne basse |

Le **prix maximal d’achat et le verdict utilisent toujours le scénario
prudent**. Le scénario central alimente le profit, le ROI et le délai
« attendus » affichés ; les trois scénarios restent visibles.

Entrées : valorisation, prix courant, coûts classés acquisition/préparation/
vente, règles de plateforme épinglées, stratégie versionnée et capital.

Sorties : coût total, produit net de vente, profit, ROI, prix maximal avant et
après arrondi, prix de mise en vente, délai et motifs.

Les formules exactes figurent dans `calculation-spec.md`. Un changement de règle
crée une nouvelle version et ne modifie aucune analyse publiée.
