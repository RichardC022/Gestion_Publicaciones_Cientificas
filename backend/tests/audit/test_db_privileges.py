"""Tests for the restricted database role of the application (TSK-72).

The role is created in the test cluster, the privileges are applied with
the same service the backend runs after ``migrate``, and the checks connect
as that role. They need committed data, hence ``transaction=True``.

Acceptance criteria: the application role can neither alter nor delete the
audit trail (on top of the trigger), keeps write access to the operational
tables, and the setup works on a fresh database and can be re-applied.
"""

from __future__ import annotations

import psycopg
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from apps.audit.models import AuditLog
from apps.audit.privileges import apply_runtime_privileges
from apps.audit.services import AuditService

ROLE = "gpc_privileges_test"
PASSWORD = "p4ss-w0rd-de-prueba"

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def runtime_role():
    apply_runtime_privileges(ROLE, PASSWORD)
    yield ROLE
    with connection.cursor() as cursor:
        cursor.execute(f'DROP OWNED BY "{ROLE}"')
        cursor.execute(f'DROP ROLE "{ROLE}"')


def as_runtime_role():
    settings = connection.settings_dict
    return psycopg.connect(
        host=settings["HOST"],
        port=settings["PORT"],
        dbname=settings["NAME"],
        user=ROLE,
        password=PASSWORD,
        autocommit=True,
    )


def denied(conn, statement: str, params=()) -> bool:
    try:
        conn.execute(statement, params)
    except psycopg.errors.InsufficientPrivilege:
        return True
    return False


class TestAuditTable:
    def test_role_can_insert_and_read_audit(self, runtime_role) -> None:
        entry = AuditService.record(action="LOGIN", entity_type="SESSION")

        with as_runtime_role() as conn:
            count = conn.execute("SELECT count(*) FROM audit_audit_log").fetchone()[0]
            conn.execute(
                "INSERT INTO audit_audit_log "
                "(event_id, occurred_at, action, entity_type, result, details, entry_hash) "
                "VALUES (gen_random_uuid(), now(), 'X', 'T', 'SUCCESS', '{}', %s)",
                ["f" * 64],
            )

        assert count == 1
        assert AuditLog.objects.filter(pk=entry.pk).exists()
        assert AuditLog.objects.count() == 2

    def test_role_cannot_update_delete_or_truncate_audit(self, runtime_role) -> None:
        AuditService.record(action="LOGIN", entity_type="SESSION")

        with as_runtime_role() as conn:
            assert denied(conn, "UPDATE audit_audit_log SET action = 'ADMIN'")
            assert denied(conn, "DELETE FROM audit_audit_log")
            assert denied(conn, "TRUNCATE audit_audit_log")

        assert AuditLog.objects.get().action == "LOGIN"

    def test_role_cannot_remove_the_protection_itself(self, runtime_role) -> None:
        with as_runtime_role() as conn:
            assert denied(conn, "ALTER TABLE audit_audit_log DISABLE TRIGGER trg_audit_no_update")
            # Sin ser dueño no puede concederse nada (PostgreSQL solo avisa).
            conn.execute("GRANT UPDATE ON audit_audit_log TO PUBLIC")
            assert denied(conn, "UPDATE audit_audit_log SET action = 'ADMIN'")
            assert denied(conn, "DROP TABLE audit_audit_log")


class TestOperationalTables:
    def test_role_keeps_write_access_to_operational_tables(self, runtime_role) -> None:
        with as_runtime_role() as conn:
            conn.execute("INSERT INTO users_role (code, name, is_active) VALUES ('PRUEBA', 'Prueba', true)")
            conn.execute("UPDATE users_role SET name = 'Otra' WHERE code = 'PRUEBA'")
            conn.execute("DELETE FROM users_role WHERE code = 'PRUEBA'")

    def test_role_is_not_privileged(self, runtime_role) -> None:
        with as_runtime_role() as conn:
            superuser, createdb, createrole = conn.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
                "WHERE rolname = current_user"
            ).fetchone()
            assert (superuser, createdb, createrole) == (False, False, False)
            assert denied(conn, "CREATE TABLE intruso (id int)")

    def test_tables_created_later_are_writable_but_not_the_audit_one(self, runtime_role) -> None:
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE tabla_posterior (id int)")
        try:
            with as_runtime_role() as conn:
                conn.execute("INSERT INTO tabla_posterior VALUES (1)")
                conn.execute("DELETE FROM tabla_posterior")
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE tabla_posterior")


class TestReapplying:
    def test_applying_twice_keeps_the_audit_restriction(self, runtime_role) -> None:
        apply_runtime_privileges(ROLE, PASSWORD)

        with as_runtime_role() as conn:
            assert denied(conn, "DELETE FROM audit_audit_log")
            conn.execute("SELECT 1 FROM audit_audit_log LIMIT 1")

    def test_restore_that_recreates_the_audit_table_is_fixed_by_reapplying(
        self, runtime_role
    ) -> None:
        # pg_restore --clean --no-privileges recrea las tablas con los permisos
        # por defecto: el rol recupera DELETE hasta que se reaplican.
        with connection.cursor() as cursor:
            cursor.execute(f'GRANT DELETE ON audit_audit_log TO "{ROLE}"')
        with as_runtime_role() as conn:
            assert not denied(conn, "DELETE FROM audit_audit_log")

        apply_runtime_privileges(ROLE, PASSWORD)

        with as_runtime_role() as conn:
            assert denied(conn, "DELETE FROM audit_audit_log")


class TestCommand:
    def test_command_requires_the_variables(self, monkeypatch) -> None:
        monkeypatch.delenv("APP_DB_USER", raising=False)
        monkeypatch.delenv("APP_DB_PASSWORD", raising=False)

        with pytest.raises(CommandError, match="obligatorias"):
            call_command("apply_db_privileges")

    def test_command_rejects_the_admin_user_as_runtime_role(self, monkeypatch) -> None:
        monkeypatch.setenv("APP_DB_USER", connection.settings_dict["USER"])
        monkeypatch.setenv("APP_DB_PASSWORD", PASSWORD)

        with pytest.raises(CommandError, match="distinto"):
            call_command("apply_db_privileges")

    def test_command_applies_the_privileges(self, monkeypatch) -> None:
        monkeypatch.setenv("APP_DB_USER", ROLE)
        monkeypatch.setenv("APP_DB_PASSWORD", PASSWORD)
        try:
            call_command("apply_db_privileges")
            with as_runtime_role() as conn:
                assert denied(conn, "DELETE FROM audit_audit_log")
        finally:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP OWNED BY "{ROLE}"')
                cursor.execute(f'DROP ROLE "{ROLE}"')
