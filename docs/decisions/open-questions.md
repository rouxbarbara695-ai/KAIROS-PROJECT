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
