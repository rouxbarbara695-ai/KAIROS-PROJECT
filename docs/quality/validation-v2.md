# Validation de la spécification V2

**Date :** 28 juillet 2026

## Contrôles réussis

- 32 fichiers, aucun fichier vide ;
- aucun lien Markdown interne cassé ;
- JSON du ruleset `1.0.0` valide ;
- poids piliers, État et qualité des preuves = 100 % ;
- schéma analysé par une grammaire PostgreSQL complète ;
- schéma central exécuté sur PostgreSQL embarqué ;
- seed : 7 plateformes et 1 ruleset ;
- opportunité manuelle créée sans `listing_id` ;
- prix manuel EUR append-only créé ;
- `analysis_impossible` publiée sans valorisation ni finance ;
- modification d’un audit et d’une analyse publiée refusée ;
- relation entre portefeuilles différents refusée.
- conversion EUR incohérente refusée ;
- création d’un job avec une règle d’accès non autorisée refusée.

## Contrôle restant en CI

L’environnement local de validation ne chargeait pas `pgcrypto` et
`btree_gist`. Leur création et la contrainte d’exclusion temporelle des règles de
plateforme ont été validées syntaxiquement, mais doivent être exécutées sur
l’image PostgreSQL réelle du projet lors de KAI-003.

Ce point n’autorise pas à supprimer les extensions ou la contrainte : il devient
un test d’intégration obligatoire de la première migration.
