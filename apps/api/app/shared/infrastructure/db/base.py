from sqlalchemy import ForeignKeyConstraint, Index
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Classe de base commune à tous les modèles SQLAlchemy. Les modèles
    doivent être un miroir exact des migrations Alembic (voir
    docs/delivery/implementation-plan-kai-001-103.md §5)."""


def portfolio_identity_index(table: str) -> Index:
    """Index unique `(portfolio_id, id)` — la cible des clés composées.

    Une clé étrangère composée ne peut désigner qu'un ensemble de colonnes
    déclaré unique. C'est cet index, et lui seul, qui rend possible
    `(portfolio_id, x_id) → (portfolio_id, id)` : sans lui, PostgreSQL refuse
    la contrainte, et l'isolation entre portefeuilles ne tiendrait plus qu'au
    code applicatif.

    Il paraît redondant avec la clé primaire `id`. Il ne l'est pas : c'est le
    couple qui doit être unique et référençable, pas seulement l'identifiant.
    """

    return Index(f"{table}_portfolio_identity_uq", "portfolio_id", "id", unique=True)


def same_portfolio_fk(column: str, target: str, name: str) -> ForeignKeyConstraint:
    """Clé étrangère composée `(portfolio_id, <colonne>) → (portfolio_id, id)`.

    C'est la barrière d'isolation la plus solide du schéma : elle rend
    **impossible en base** qu'une ligne d'un portefeuille référence une ligne
    d'un autre. Le contrôle applicatif (`Principal.owns_portfolio`) reste la
    première défense, mais il ne peut pas garantir ce que la base garantit ici
    — une erreur de code ne peut pas produire une relation croisée.

    Déclarée ici plutôt qu'écrite trente fois : la répétition invite la faute
    de frappe, et une faute de frappe sur une clé étrangère ne se voit pas.
    """

    return ForeignKeyConstraint(
        ["portfolio_id", column],
        [f"{target}.portfolio_id", f"{target}.id"],
        name=name,
    )
