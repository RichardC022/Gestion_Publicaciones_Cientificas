"""Database privileges of the application role (TSK-72, plan section 1.20).

The backend connects at runtime as a dedicated, non-superuser role. That
role gets ``SELECT``/``INSERT``/``UPDATE``/``DELETE`` on the operational
tables but only ``SELECT``/``INSERT`` on ``audit_audit_log``: it cannot
rewrite or erase the audit trail, on top of the append-only trigger. The
administrative role (``POSTGRES_USER``) owns the schema and is the only
one that migrates; a superuser ignores ``GRANT``/``REVOKE``, so the
runtime role must not be one.

:func:`apply_runtime_privileges` is idempotent. It runs after every
``migrate`` (and so after a restore, because dumps are taken with
``--no-privileges``) and re-applies the whole set, including the audit
restriction on a table the migrations just created.
"""

from __future__ import annotations

from django.db import connection, transaction
from psycopg import sql

AUDIT_TABLE = "audit_audit_log"
OPERATIONAL_PRIVILEGES = sql.SQL("SELECT, INSERT, UPDATE, DELETE")


def _run(statements: list[sql.Composable]) -> None:
    connection.ensure_connection()
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement.as_string(connection.connection))


def apply_runtime_privileges(role: str, password: str) -> None:
    """Create ``role`` if needed and grant it the restricted privileges."""
    who = sql.Identifier(role)
    with transaction.atomic():
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user, current_database()")
            owner, database = cursor.fetchone()
            cursor.execute("SELECT to_regclass(%s)", [f"public.{AUDIT_TABLE}"])
            has_audit_table = cursor.fetchone()[0] is not None
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
            exists = cursor.fetchone() is not None

        statements: list[sql.Composable] = []
        if not exists:
            statements.append(sql.SQL("CREATE ROLE {}").format(who))
        statements += [
            sql.SQL(
                "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION PASSWORD {}"
            ).format(who, sql.Literal(password)),
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database), who
            ),
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(who),
            sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(who),
            sql.SQL("GRANT {} ON ALL TABLES IN SCHEMA public TO {}").format(
                OPERATIONAL_PRIVILEGES, who
            ),
            sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                who
            ),
            # Tablas y secuencias que cree una migración futura.
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT {} ON TABLES TO {}"
            ).format(sql.Identifier(owner), OPERATIONAL_PRIVILEGES, who),
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                "GRANT USAGE, SELECT ON SEQUENCES TO {}"
            ).format(sql.Identifier(owner), who),
        ]
        if has_audit_table:
            statements += [
                sql.SQL("REVOKE ALL ON TABLE {} FROM {}").format(
                    sql.Identifier(AUDIT_TABLE), who
                ),
                sql.SQL("GRANT SELECT, INSERT ON TABLE {} TO {}").format(
                    sql.Identifier(AUDIT_TABLE), who
                ),
            ]
        _run(statements)
