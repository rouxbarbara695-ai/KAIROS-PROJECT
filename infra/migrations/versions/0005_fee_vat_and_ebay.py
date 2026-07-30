"""TVA sur commission, frais de paiement, et eBay parmi les plateformes.

Trois manques constatés en relevant les grilles tarifaires officielles.

Une plateforme peut annoncer ses frais hors taxe et ajouter la TVA à la
facture. Pour un vendeur particulier, qui ne la récupère pas, cette taxe est un
coût sec : une commission de 12,5 % lui coûte 15 %. Faute de la modéliser, tout
profit de revente était surestimé d'un cinquième de la commission, sans que
rien ne le signale.

Les frais de traitement du paiement sont tenus à part de la commission : ils
s'appliquent au prix de vente, ils ne portent pas de TVA — ce sont des frais
financiers — et toutes les plateformes ne les facturent pas.

eBay manquait à la liste des plateformes. Une revente qui s'y fait n'était donc
pas modélisable du tout, et aucun écran ne le disait.

`if not exists` / `on conflict do nothing` parce que `0001` rejoue
`database/schema.sql` d'un bloc : sur une base neuve tout existe déjà à
l'arrivée ici, sur une base existante non.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        alter table platform_rules
          add column if not exists buyer_fee_vat_rate numeric(18,10),
          add column if not exists seller_fee_vat_rate numeric(18,10),
          add column if not exists payment_fee_rate numeric(18,10);
        """
    )

    # Un taux au-delà de 1 trahit une saisie en pourcentage prise pour un taux
    # décimal : 20 au lieu de 0.20 multiplierait la commission par vingt.
    for column in ("buyer_fee_vat_rate", "seller_fee_vat_rate", "payment_fee_rate"):
        op.execute(
            f"""
            alter table platform_rules
              drop constraint if exists platform_rules_{column}_range;
            alter table platform_rules
              add constraint platform_rules_{column}_range
              check ({column} is null or ({column} >= 0 and {column} <= 1));
            """
        )

    op.execute(
        """
        insert into platforms (id, code, name) values
          ('00000000-0000-0000-0000-000000000008', 'ebay', 'eBay')
        on conflict (id) do nothing;
        """
    )


def downgrade() -> None:
    # eBay n'est pas retiré : une opportunité peut déjà s'y rattacher, et la
    # supprimer casserait sa clé étrangère. Une plateforme de trop ne fausse
    # aucun calcul ; une opportunité orpheline, si.
    for column in ("buyer_fee_vat_rate", "seller_fee_vat_rate", "payment_fee_rate"):
        op.execute(
            f"alter table platform_rules "
            f"drop constraint if exists platform_rules_{column}_range;"
        )
    op.execute(
        """
        alter table platform_rules
          drop column if exists buyer_fee_vat_rate,
          drop column if exists seller_fee_vat_rate,
          drop column if exists payment_fee_rate;
        """
    )
