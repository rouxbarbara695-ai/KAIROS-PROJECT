# Prompt de lancement pour Claude

Copier ce prompt dans Claude après avoir ajouté ce dossier au projet :

> Tu interviens comme lead developer sur KAIROS. Lis intégralement `CLAUDE.md`
> et tous les documents qu’il impose, sans commencer à coder. Réalise d’abord
> un audit de cohérence entre le PRD, les calculs, le contrat API et
> `database/schema.sql`. Présente les contradictions ou décisions bloquantes,
> sans inventer de réponse métier. Ensuite, propose un plan d’implémentation
> détaillé pour KAI-001 à KAI-103, avec arborescence, migrations, contrats,
> tests et critères de validation. Attends ma validation avant de créer le
> code. Les valeurs de `docs/decisions/open-questions.md` restent configurables.
> Ne développe aucun scraper réel, paiement, ML ou fonctionnalité hors MVP.

## Après validation du plan

Demander :

> Implémente uniquement le lot validé. Exécute formatage, typage, migrations et
> tests. À la fin, fournis les fichiers modifiés, les commandes de validation,
> les résultats, les limites connues et les décisions restant ouvertes. Ne
> marque aucune story comme terminée si sa Definition of Done n’est pas remplie.

## Contrôle humain conseillé

Avant le premier code, valider dans `docs/decisions/open-questions.md` les seuils
de score, la prime du full set, le profil fiscal et les méthodes d’accès aux
plateformes. Le socle local et la saisie manuelle peuvent commencer sans ces
décisions ; la recommandation commerciale et la collecte automatique non.
