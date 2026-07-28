# Règles propres aux plateformes

Une `PlatformRule` est immuable et sélectionnée par plateforme, région et date :
`valid_from ≤ analyzed_at` et (`valid_to` est `null` ou
`analyzed_at < valid_to`). Deux règles de même portée ne peuvent se chevaucher.

Après création, seul `valid_to` peut être fixé une fois pour clôturer la période ;
les frais, accès et autres attributs ne peuvent jamais être modifiés.

## Contrat

| Groupe | Champs |
|---|---|
| Identité | plateforme, région, version, validité, source, vérifiée le |
| Accès | `manual|assisted_import|official_api|partner`, autorisé, fréquence min/max |
| Frais acheteur | taux, fixe, assiette, minimum, maximum, devise |
| Frais vendeur | taux, fixe, assiette, minimum, maximum, devise |
| Paiement/change | prestataire, frais, devise et assiette |
| Livraison | obligatoire, responsable, incluse ou non |
| Protection | authentification, séquestre, garantie, recours |
| Fiscalité | profil requis, douane/TVA connue ou inconnue |
| Observabilité | annonce active, résultat d’enchère, vente réalisée observable |

Les valeurs absentes sont `null` et produisent avertissement ou blocage selon le
scénario. Aucune valeur n’est déduite du nom de la plateforme.

## Sources

| Source | Nature de prix à distinguer |
|---|---|
| Chrono24 | demandé, baisse, prix d’achat/vente interne confirmé |
| Catawiki | enchère courante, marteau, frais acheteur, résultat |
| Vestiaire Collective | demandé, offre, offre acceptée, achat/vente confirmé |
| Fournisseur de cote | estimation externe, jamais vente réalisée par défaut |
| Marchand | prix demandé, garantie, vente uniquement si documentée |
| Donnée KAIROS | prix payé/vendu confirmé avec provenance |

## Règles particulières

### Chrono24

Dédupliquer sur l’identifiant externe. Une disparition ne prouve pas la vente.
Trusted Checkout, signature, livraison, vues et favoris sont des attributs
séparés. Les vues/favoris sont des signaux de liquidité, pas des transactions.

### Catawiki

Conserver `current_bid`, `hammer_price`, `reserve_met`, `auction_end_at` et
`buyer_fees` séparément. Le prix maximal d’enchère est le prix marteau maximal
obtenu par inversion des frais. Au-dessus, conserver l’historique et proposer
`abandoned` avec `MAX_BID_EXCEEDED`.

### Vestiaire Collective

Séparer prix demandé, offre envoyée, acceptée, paiement et acquisition. Une
offre acceptée ne suffit pas à créer un achat.

### Hors UE

Douane et fiscalité sont des coûts explicites. Sans profil fiscal et borne
prudente, `buy` est impossible. KAIROS ne suppose ni TVA récupérable ni régime
de marge.

## Conformité

La seed V1 autorise uniquement `manual` et `assisted_import=false` par défaut.
Avant tout connecteur, une décision écrite doit identifier base légale/CGU,
méthode, données, fréquence, conservation et arrêt d’urgence. Aucun
contournement d’authentification, de protection ou de limite n’est permis.
