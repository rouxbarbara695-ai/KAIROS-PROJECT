"""Barèmes par tranches et base de commission.

Deux manques révélés par la grille réelle d'eBay France.

**Les tranches.** eBay prélève 10 % sur les 2 000 premiers euros de la vente
puis 2 % au-delà. C'est un barème marginal, comme l'impôt : sur une vente à
10 000 €, la commission vaut 360 € et non 200 €. Notre modèle ne portait qu'un
taux unique, dont le taux effectif réel varie de 10,4 % à 4,0 % selon le
montant — aucune valeur fixe n'aurait été juste à plus de quelques centaines
d'euros près.

**La base.** eBay commissionne le montant total payé par l'acheteur, frais de
port compris ; Chrono24 le seul prix de la montre. Supposer l'une des deux
plutôt que de la lire reviendrait à inventer une règle.

Les colonnes `buyer_fee_basis` et `seller_fee_basis` existaient déjà, en texte
libre et jamais lues. Elles reçoivent ici une valeur par défaut, une contrainte
de domaine et un sens.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_BASIS_COLUMNS = ("buyer_fee_basis", "seller_fee_basis")
_TIER_COLUMNS = ("buyer_fee_tiers", "seller_fee_tiers")


def upgrade() -> None:
    for column in _TIER_COLUMNS:
        op.execute(
            f"""
            alter table platform_rules
              add column if not exists {column} jsonb not null default '[]'::jsonb;
            alter table platform_rules
              drop constraint if exists platform_rules_{column}_is_array;
            alter table platform_rules
              add constraint platform_rules_{column}_is_array
              check (jsonb_typeof({column}) = 'array');
            """
        )

    # Le déclencheur d'immuabilité n'autorise qu'une chose sur une grille
    # existante : la fermer. Il a raison — une commission réécrite rendrait
    # inexplicable une analyse déjà publiée. Mais il vise les écritures
    # métier, pas une migration de schéma : remplir une colonne qui n'a jamais
    # été lue ne change aucun calcul. On le suspend donc le temps du
    # remplissage, et on le rétablit aussitôt.
    op.execute("alter table platform_rules disable trigger platform_rules_close_only;")
    try:
        for column in _BASIS_COLUMNS:
            # Une grille existante commissionne le seul prix : c'est ce que le
            # moteur faisait jusqu'ici, et changer ce comportement en silence
            # modifierait le résultat d'analyses déjà publiées.
            op.execute(
                f"""
                alter table platform_rules
                  alter column {column} set default 'price';
                update platform_rules set {column} = 'price' where {column} is null;
                alter table platform_rules
                  alter column {column} set not null;
                alter table platform_rules
                  drop constraint if exists platform_rules_{column}_known;
                alter table platform_rules
                  add constraint platform_rules_{column}_known
                  check ({column} in ('price', 'price_and_shipping'));
                """
            )
    finally:
        op.execute(
            "alter table platform_rules enable trigger platform_rules_close_only;"
        )


def downgrade() -> None:
    for column in _TIER_COLUMNS:
        op.execute(
            f"""
            alter table platform_rules
              drop constraint if exists platform_rules_{column}_is_array;
            alter table platform_rules drop column if exists {column};
            """
        )
    for column in _BASIS_COLUMNS:
        op.execute(
            f"""
            alter table platform_rules
              drop constraint if exists platform_rules_{column}_known;
            alter table platform_rules alter column {column} drop not null;
            alter table platform_rules alter column {column} drop default;
            """
        )
