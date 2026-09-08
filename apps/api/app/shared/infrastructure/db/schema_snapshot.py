"""Photographie structurelle du schéma PostgreSQL après toutes les migrations.

**Pourquoi pas un `diff` de `pg_dump`.** La CI comparait autrefois la sortie de
`pg_dump --schema-only` au fichier `database/schema.sql`. Cette comparaison ne
pouvait rien détecter, pour deux raisons distinctes :

1. `pg_dump` écrit dans son propre style — ordre, guillemets, `ALTER TABLE`
   séparés — qui ne ressemble pas à du SQL écrit à la main. Le diff comptait
   plusieurs milliers de lignes sur un schéma pourtant identique, et la CI
   l'exécutait avec `|| true`, donc sans jamais échouer.
2. Surtout, les deux fichiers **ne décrivent pas le même objet**.
   `database/schema.sql` est le schéma **initial**, celui que la migration
   `0001` exécute tel quel. Les migrations `0002` à `0007` le font ensuite
   évoluer. Les comparer revenait à reprocher à un schéma d'avoir été migré.

Ce module compare ce qui doit l'être : **l'état obtenu après toutes les
migrations**, décrit structurellement plutôt que textuellement. Types, nullité,
valeurs par défaut, contraintes, index et déclencheurs sont extraits du
catalogue, triés, et sérialisés en JSON stable. Une dérive se lit alors comme
quelques lignes de diff nommées, pas comme un mur de SQL reformaté.

Ce que cet instantané attrape et qu'`alembic check` ne voit pas : les
déclencheurs d'immuabilité, les contraintes `check`, les contraintes
d'exclusion et les types énumérés — tout ce que SQLAlchemy ne modélise pas et
qui porte pourtant l'essentiel des garanties du schéma.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# `alembic_version` est un détail d'outillage, pas une table du domaine : son
# contenu varie à chaque migration et n'a rien à figer.
_EXCLUDED_TABLES = ("alembic_version",)

_COLUMNS_SQL = """
select c.relname as table_name,
       a.attname as column_name,
       format_type(a.atttypid, a.atttypmod) as data_type,
       a.attnotnull as not_null,
       pg_get_expr(d.adbin, d.adrelid) as default_expr
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
join pg_attribute a on a.attrelid = c.oid
left join pg_attrdef d on d.adrelid = c.oid and d.adnum = a.attnum
where n.nspname = 'public'
  and c.relkind = 'r'
  and a.attnum > 0
  and not a.attisdropped
  and c.relname <> all(:excluded)
order by c.relname, a.attname
"""

_CONSTRAINTS_SQL = """
select c.relname as table_name,
       con.conname as constraint_name,
       pg_get_constraintdef(con.oid) as definition
from pg_constraint con
join pg_class c on c.oid = con.conrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname <> all(:excluded)
order by c.relname, con.conname
"""

_INDEXES_SQL = """
select tablename as table_name, indexname as index_name, indexdef as definition
from pg_indexes
where schemaname = 'public'
  and tablename <> all(:excluded)
order by tablename, indexname
"""

_TRIGGERS_SQL = """
select c.relname as table_name,
       t.tgname as trigger_name,
       pg_get_triggerdef(t.oid) as definition
from pg_trigger t
join pg_class c on c.oid = t.tgrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and not t.tgisinternal
  and c.relname <> all(:excluded)
order by c.relname, t.tgname
"""

_ENUMS_SQL = """
select t.typname as enum_name, e.enumlabel as label
from pg_type t
join pg_enum e on e.enumtypid = t.oid
join pg_namespace n on n.oid = t.typnamespace
where n.nspname = 'public'
order by t.typname, e.enumsortorder
"""


async def capture_schema(connection: AsyncConnection) -> dict[str, Any]:
    """Retourne la structure du schéma `public`, triée et sérialisable.

    Le tri est fait en SQL et en Python : deux exécutions sur deux machines
    doivent produire exactement le même document, sans quoi l'instantané
    signalerait des dérives qui n'existent pas et finirait ignoré.
    """

    params = {"excluded": list(_EXCLUDED_TABLES)}

    tables: dict[str, dict[str, Any]] = {}

    for row in (await connection.execute(text(_COLUMNS_SQL), params)).mappings():
        table = tables.setdefault(
            row["table_name"], {"columns": {}, "constraints": {}, "indexes": {}}
        )
        table["columns"][row["column_name"]] = {
            "type": row["data_type"],
            "nullable": not row["not_null"],
            "default": row["default_expr"],
        }

    for row in (await connection.execute(text(_CONSTRAINTS_SQL), params)).mappings():
        table = tables.setdefault(
            row["table_name"], {"columns": {}, "constraints": {}, "indexes": {}}
        )
        table["constraints"][row["constraint_name"]] = row["definition"]

    for row in (await connection.execute(text(_INDEXES_SQL), params)).mappings():
        table = tables.setdefault(
            row["table_name"], {"columns": {}, "constraints": {}, "indexes": {}}
        )
        table["indexes"][row["index_name"]] = row["definition"]

    triggers: dict[str, dict[str, str]] = {}
    for row in (await connection.execute(text(_TRIGGERS_SQL), params)).mappings():
        triggers.setdefault(row["table_name"], {})[row["trigger_name"]] = row[
            "definition"
        ]

    enums: dict[str, list[str]] = {}
    for row in (await connection.execute(text(_ENUMS_SQL))).mappings():
        enums.setdefault(row["enum_name"], []).append(row["label"])

    return {
        "description": (
            "État du schéma après toutes les migrations. Régénérer avec "
            "`make schema-snapshot`. Ne pas confondre avec database/schema.sql, "
            "qui est le schéma initial exécuté par la migration 0001."
        ),
        "tables": tables,
        "triggers": triggers,
        "enums": enums,
    }
