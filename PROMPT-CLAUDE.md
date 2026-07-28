# Prompt de lancement pour Claude

## Première tâche

Coller le prompt suivant dans Claude Code après avoir remplacé le contenu du
dépôt par cette V2 :

> Tu interviens comme lead developer sur KAIROS. Lis intégralement `CLAUDE.md`
> puis tous les documents de son ordre de lecture. La V2 intègre déjà les deux
> audits précédents : vérifie d’abord, sans coder, que chaque point de
> `docs/decisions/audit-resolution-v2.md` est effectivement réconcilié dans le
> PRD, les calculs, l’API et `database/schema.sql`. Ne relance pas un audit
> général sans fin : signale uniquement les contradictions résiduelles qui
> bloqueraient KAI-001 à KAI-103. Propose ensuite un plan d’implémentation
> détaillé de ce seul lot, avec arborescence, migrations, endpoints, tests et
> critères de validation. Attends ma validation avant tout code. N’ajoute ni
> collecteur réel, ni paiement, ni ML, ni fonctionnalité hors lot.

## Après validation du plan

> Implémente KAI-001 à KAI-103 sur une branche séparée. Respecte strictement le
> schéma, le contrat API et les décisions V2. Exécute formatage, typage,
> migrations sur base vide, tests et lint. À la fin, fournis le résumé des
> fichiers modifiés, les commandes exécutées, leurs résultats, les limites
> connues et les questions encore ouvertes. Ne marque aucune story comme
> terminée si sa Definition of Done n’est pas remplie.

## Limite d’autonomie

Claude peut choisir l’organisation interne du code si elle respecte
`overview.md`. Il ne peut pas modifier seul une formule, un code de porte, un
statut, un contrat public, un seuil métier ou une décision adoptée.
