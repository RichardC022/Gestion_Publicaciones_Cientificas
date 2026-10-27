"""Append-only trigger for the audit trail (plan section 1.20).

``UPDATE`` and ``DELETE`` over ``audit_audit_log`` fail at the database
level; the application user also lacks those privileges (TSK-72 adds the
second barrier). Reversible for development.
"""

from __future__ import annotations

from django.db import migrations

TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION prevent_audit_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'La auditoría es append-only';
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGER = """
CREATE TRIGGER trg_audit_no_update
BEFORE UPDATE OR DELETE ON audit_audit_log
FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
"""

DROP_TRIGGER = "DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_audit_log;"
DROP_FUNCTION = "DROP FUNCTION IF EXISTS prevent_audit_mutation();"


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=TRIGGER_FUNCTION + CREATE_TRIGGER,
            reverse_sql=DROP_TRIGGER + "\n" + DROP_FUNCTION,
        ),
    ]
