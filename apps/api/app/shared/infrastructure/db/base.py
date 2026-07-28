from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Classe de base commune à tous les modèles SQLAlchemy. Les modèles
    doivent être un miroir exact des migrations Alembic (voir
    docs/delivery/implementation-plan-kai-001-103.md §5)."""
