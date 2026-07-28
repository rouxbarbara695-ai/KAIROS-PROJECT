# Moteur d’analyse d’opportunité

Le moteur transforme une annonce ou une saisie manuelle en décision
reproductible.

> L’utilisateur sélectionne l’opportunité ; KAIROS structure et calcule
> l’intelligence disponible.

## Enchaînement

1. Valider le portefeuille et la source manuelle ou URL.
2. Enregistrer les données brutes sans les écraser.
3. Confirmer l’identité ou qualifier l’incertitude.
4. Évaluer les cinq portes aux codes stables.
5. Si une porte bloque, publier `analysis_impossible` ou `pass` sans score ni
   valeurs financières obligatoires.
6. Sinon, construire la valorisation, les trois scénarios, le prix maximal, le
   délai, le score et le verdict.
7. Épingler les versions et snapshots utilisés.
8. Publier une nouvelle analyse ; ne jamais modifier la précédente.

## Modes d’entrée

- `manual` : identifiant manuel unique dans le portefeuille, prix et données
  renseignés par l’utilisateur ;
- `url` : URL canonicalisée et identifiant externe si disponible ;
- `assisted_import` : transformation explicite d’un fichier ou contenu fourni ;
- `connector` : uniquement après validation du mode d’accès.

Un échec d’import bascule vers le formulaire manuel sans perte de saisie.

## Évolution future

La surveillance et la découverte automatiques sont des étapes conditionnelles.
Elles ne font pas partie du contrat du premier lot et n’autorisent aucun
scraping implicite.
