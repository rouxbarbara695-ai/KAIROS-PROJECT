# Règles propres aux plateformes

Ce document définit le modèle d’adaptation. Les taux sont des données
versionnées, pas des constantes. À la date d’analyse, KAIROS choisit la règle
dont `valid_from ≤ date < valid_to`.

| Plateforme | Nature | Prix à capter | Particularités à modéliser |
|---|---|---|---|
| Chrono24 | annonces / transaction sécurisée | demandé, baisses, prix utilisateur réalisé | commission vendeur, Trusted Checkout, expédition/signature, statut parfois non observable |
| Catawiki | enchères | enchère, résultat, frais acheteur | heure de fin, réserve, incréments, frais variables, enchère dans les 24 h |
| Vestiaire Collective | annonce/offre | demandé, offre acceptée, résultat utilisateur | offre, annulation, authentification, commission, transport |
| WatchCharts | fournisseur de cote | estimation externe | fréquence, licence/API, historique, ne jamais appeler “vente réalisée” |
| Watchfinder / marchand | stock professionnel | demandé | garantie incluse, prime marchand, prix réalisé généralement inconnu |
| Boutique indépendante | marchand | demandé/réalisé si documenté | TVA/marge, garantie, négociation hors plateforme |
| Donnée utilisateur | opération interne | prix réellement payé/vendu | confiance A si justificatif ou saisie confirmée |

## Contrat `PlatformRule`

- plateforme et pays/région ;
- dates de validité ;
- commission acheteur : taux, fixe, assiette, minimum, maximum ;
- commission vendeur : mêmes champs ;
- paiement et change ;
- livraison obligatoire/facultative et responsable ;
- authentification/garantie ;
- fiscalité ou douane applicable/inconnue ;
- capacité d’observer une vente réellement réalisée ;
- méthode d’accès autorisée : manuel, API, partenaire, import assisté ;
- fréquence minimale et maximale ;
- provenance et date de vérification.

## Chrono24

Dédupliquer sur l’identifiant d’annonce. Une disparition n’est pas une vente.
La commission configurée pour l’opération utilisateur est appliquée à la date
de la vente. Les favoris et vues sont des signaux facultatifs de liquidité,
jamais des preuves. Une annonce d’un marchand peut inclure une prime de garantie
et doit être distinguée d’une vente entre particuliers.

## Catawiki

Conserver `current_bid`, `hammer_price`, `reserve_met`, `auction_end_at` et
`buyer_fees` séparément. Dans les 24 dernières heures, la fréquence cible peut
passer à une heure. Le prix maximal d’enchère est le prix marteau maximal après
résolution inverse des frais. Si l’enchère dépasse ce maximum, statut
`abandoned` avec motif `MAX_BID_EXCEEDED`; l’historique est conservé.

## Vestiaire Collective

Séparer prix demandé, offre envoyée, offre acceptée et paiement. Une offre
acceptée n’est pas une acquisition tant que l’achat n’est pas confirmé. Les
conditions d’annulation relèvent d’un affichage informatif et ne doivent pas
être extrapolées : elles sont stockées avec leur source et date.

## Extra-UE

Si vendeur hors zone douanière de destination, les droits et taxes sont des
entrées obligatoires ou un scénario prudent. Sans estimation exploitable,
KAIROS bloque Acheter mais permet Surveiller. La TVA récupérable ou régime de
marge n’est jamais supposé ; un profil fiscal explicite est requis.

## Collecte et conformité

Avant d’activer un connecteur : documenter autorisation, robots/CGU, API
disponible, limites, données personnelles, conservation et mécanisme d’arrêt.
Le MVP accepte des imports manuels/assistés. Aucun contournement de protection,
authentification ou limite n’est autorisé.
