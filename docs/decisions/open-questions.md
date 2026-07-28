# Questions encore ouvertes

Ces sujets ne bloquent pas KAI-001 à KAI-103. Claude peut créer des ports et
configurations, mais ne doit ni activer ni inventer une réponse.

| ID | Question | Valeur V1 conservatrice | Bloque |
|---|---|---|---|
| Q-01 | fournisseur d’authentification | aucun en local | exposition Internet |
| Q-02 | hébergement et stockage objet | ports abstraits | déploiement |
| Q-03 | fournisseur de taux FX | port + taux EUR=1 en test | calcul réel non EUR |
| Q-04 | accès Chrono24 | manuel uniquement | KAI-405 Chrono24 |
| Q-05 | accès Catawiki | manuel uniquement | KAI-405 Catawiki |
| Q-06 | accès Vestiaire | manuel uniquement | KAI-405 Vestiaire |
| Q-07 | profil fiscal hors UE | `buy` bloqué sans saisie | recommandation extra-UE |
| Q-08 | conservation des images/pages | aucune page brute par défaut | import externe |
| Q-09 | seuils de profit par segment | règles V1 globales | calibration bêta |
| Q-10 | validation des primes de set | +10 % / +20 % versionnées | calibration bêta |

Une décision modifiant un calcul crée un nouveau ruleset. Une décision d’accès
plateforme crée une nouvelle `PlatformRule`; elle ne modifie pas l’historique.
