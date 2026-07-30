# Questions encore ouvertes

Ces sujets ne bloquent pas KAI-001 à KAI-103. Claude peut créer des ports et
configurations, mais ne doit ni activer ni inventer une réponse.

| ID | Question | Valeur V1 conservatrice | Bloque |
|---|---|---|---|
| Q-01 | fournisseur d’authentification | aucun en local | exposition Internet |
| Q-02 | hébergement et stockage objet | ports abstraits | déploiement |
| Q-03 | fournisseur de taux FX | port + taux EUR=1 en test | calcul réel non EUR — **dépriorisé, voir ci-dessous** |
| Q-04 | accès Chrono24 | manuel uniquement | KAI-405 Chrono24 |
| Q-05 | accès Catawiki | manuel uniquement | KAI-405 Catawiki |
| Q-06 | accès Vestiaire | manuel uniquement | KAI-405 Vestiaire |
| Q-07 | profil fiscal hors UE | `buy` bloqué sans saisie | recommandation extra-UE |
| Q-08 | conservation des images/pages | aucune page brute par défaut | import externe |
| Q-09 | seuils de profit par segment | règles V1 globales | calibration bêta |
| Q-10 | validation des primes de set | +10 % / +20 % versionnées | calibration bêta |
| Q-11 | méthode de quantile pour `Q1`/`Q3` | charnières de Tukey | repli IQR des anomalies |
| Q-12 | dimension d'état et écart de set gouvernant la similarité | écart le plus défavorable ; au-delà de deux niveaux, coefficient le plus bas | pondération des comparables |
| Q-13 | dérogation au plafond d'immobilisation pour une affaire exceptionnelle | seuils provisoires ci-dessous, ruleset 1.1.0 | calibration fondateur |

Une décision modifiant un calcul crée un nouveau ruleset. Une décision d’accès
plateforme crée une nouvelle `PlatformRule`; elle ne modifie pas l’historique.

## Q-03 — précisions

**Arbitrage retenu : sujet déprioritisé.** La plupart des plateformes
permettent de choisir sa devise d’affichage, donc le parcours réel produit
majoritairement des montants déjà en euros. La conversion automatique n’est
pas sur le chemin critique de la V1.

Conséquence assumée : tant qu’aucune source n’alimente `fx_rates`, un montant
saisi dans une devise autre que l’euro est enregistré avec sa devise source et
signalé par un avertissement, sans équivalent EUR. Le parcours manuel reste
utilisable (règle 8), aucune donnée n’est perdue, et aucun taux n’est inventé.

**Google n’est pas retenu comme source.** Il n’existe pas d’interface publique
documentée pour les cours affichés par Google ; les récupérer supposerait de
lire la page de résultats, ce qui contrevient à ses conditions d’utilisation et
ne donne aucune garantie de stabilité, d’horodatage ni de traçabilité — or la
règle 3 impose de conserver la source et l’horodatage du taux.

**Candidat proposé quand le sujet sera repris :** les taux de référence
quotidiens de la Banque centrale européenne, qui sont publics, documentés,
horodatés, et pivotés sur l’euro — ce qui correspond exactement à la devise de
référence de KAIROS. Reste à confirmer, ainsi que la fraîcheur acceptable
(`fx_max_age_hours`, aujourd’hui 24 h par configuration).


## Q-13 — dérogation au plafond d'immobilisation

**Demande du fondateur** : pouvoir déroger au plafond lorsque l'affaire est
excellente, avec une liquidité et une marge très supérieures aux minimums.

L'intention est légitime et le raisonnement tient : le plafond d'immobilisation
existe parce qu'un capital déjà bloqué le reste longtemps. Si la pièce achetée
se revend vite, ce risque précis disparaît en grande partie. La dérogation est
donc conditionnée d'abord à la liquidité, et non au seul profit.

**Seuils provisoires retenus**, tous simultanés :

| Condition | Seuil | Raison |
|---|---|---|
| Pilier liquidité | ≥ 75 | la pièce se revend vite : l'immobilisation est courte |
| ROI central | ≥ 25 % | très au-dessus du minimum de stratégie (10 %) |
| Profit central | ≥ 400 € | très au-dessus du minimum de stratégie (200 €) |
| `valuation_confidence` | ≥ 70 | une affaire en apparence excellente sur une preuve faible n'en est pas une |

**Effet** : le plafond passe de 54 à 79. Il n'est pas supprimé — une position
déjà immobilisée à plus de 70 % reste une position tendue, et le verdict
`buy` redevient possible sans que le score puisse atteindre l'excellence.

La dérogation apparaît dans la trace comme telle, avec ses quatre conditions et
leurs valeurs constatées : elle doit être visible, jamais silencieuse.

**Ces quatre seuils sont des valeurs provisoires à calibrer.** Ils vivent dans
le ruleset `1.1.0`, versionné et immuable comme les autres : modifier un calcul
crée un nouveau ruleset, il ne réécrit pas l'ancien. Les analyses déjà publiées
sous `1.0.0` restent rejouables à l'identique.


## Q-14 — quels champs comptent dans la qualité de la fiche

`scoring-engine.md` définit la qualité de la fiche comme « champs utiles
renseignés / champs applicables » sans énumérer les champs. Le rapport est donc
parfaitement spécifié, mais son dénominateur ne l'est pas.

**Liste provisoire retenue**, celle du parcours manuel actuel : marque,
référence, statut de la référence, état mécanique, état cosmétique,
originalité, boîte, papiers, prix, pays du vendeur, type de vendeur,
plateforme.

Deux points à trancher :

1. **Le périmètre.** Faut-il compter des champs que le parcours manuel ne
   demande pas encore — photos, description d'origine, numéro de série ? Les
   ajouter ferait mécaniquement baisser la note de toutes les fiches
   existantes, ce qui est acceptable pour une note relative mais doit être
   décidé, pas subi.
2. **La pondération.** La spécification décrit un rapport simple, sans poids.
   Une référence manquante et un type de vendeur manquant pèsent donc
   identiquement, alors que le premier empêche presque toute comparaison et
   que le second n'est qu'un confort.

Un champ sans objet pour le dossier — la plateforme pour une vente de
particulier à particulier — n'entre ni au numérateur ni au dénominateur.
Le pénaliser reviendrait à noter un dossier complet comme incomplet.

**Cette liste est provisoire.** Elle vit dans le ruleset `1.2.0`, versionné et
immuable : l'allonger crée un nouveau ruleset et laisse les analyses déjà
publiées rejouables à l'identique.

## Q-15 — statut fiscal du revendeur et TVA sur les commissions

Une plateforme peut annoncer ses frais hors taxe et ajouter la TVA à sa
facture. Catawiki l'écrit explicitement pour son côté vendeur ; côté acheteur,
ses frais sont annoncés taxe comprise. Chrono24 ne le précise pas.

Que cette TVA soit un coût dépend du statut du revendeur :

- **vendeur particulier** — la taxe n'est pas récupérable, elle sort du
  profit ; une commission de 12,5 % coûte réellement 15 % ;
- **entreprise assujettie** — la taxe est déductible, la commission reste à
  12,5 % dans le calcul de marge, et la TVA collectée sur la vente relève d'un
  sujet distinct que KAIROS ne traite pas.

**Position retenue pour le MVP** : vendeur particulier, TVA non récupérable.
C'est l'hypothèse la plus prudente — elle ne surestime jamais le profit — et
c'est le statut déclaré par l'utilisateur du MVP.

**Ce n'est pas codé en dur.** Le taux est saisi par grille de plateforme
(`buyer_fee_vat_rate`, `seller_fee_vat_rate`), versionné avec elle, et un taux
absent n'ajoute rien plutôt que de supposer une valeur. Passer en société
assujettie consiste à enregistrer de nouvelles grilles à 0, pas à modifier du
code.

Deux points restent à trancher :

1. **Le taux applicable.** 20 % suppose une facturation en France. Une
   plateforme établie hors de France peut facturer sans TVA, ou avec le taux de
   son pays selon les règles d'autoliquidation. Le taux est donc saisi par
   grille et non déduit d'une constante nationale.
2. **La TVA sur la vente elle-même.** Hors périmètre : un particulier qui
   revend un bien d'occasion ne collecte pas de TVA. Si le statut change, c'est
   une story à part entière, distincte de la TVA sur commission.
