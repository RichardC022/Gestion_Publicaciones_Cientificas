"""Database triggers that protect the editorial history (plan section 1.20).

* ``DELETE`` over ``publications_manuscript`` fails: only logical
  withdrawal is allowed.
* ``UPDATE`` and ``DELETE`` over ``publications_manuscript_version`` fail:
  every formal submission is immutable.
* ``UPDATE`` and ``DELETE`` over ``publications_status_event`` fail through
  the generic ``prevent_append_only_mutation`` function, which the verdict
  trigger of TSK-50 reuses.

Reversible for development.
"""

from __future__ import annotations

from django.db import migrations

CREATE_TRIGGERS = """
CREATE OR REPLACE FUNCTION prevent_manuscript_delete()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Los manuscritos solo admiten baja lógica';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_manuscript_no_delete
BEFORE DELETE ON publications_manuscript
FOR EACH ROW EXECUTE FUNCTION prevent_manuscript_delete();

CREATE OR REPLACE FUNCTION prevent_version_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Las versiones son inmutables';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_version_no_update
BEFORE UPDATE OR DELETE ON publications_manuscript_version
FOR EACH ROW EXECUTE FUNCTION prevent_version_mutation();

CREATE OR REPLACE FUNCTION prevent_append_only_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'El registro es append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_status_event_no_update
BEFORE UPDATE OR DELETE ON publications_status_event
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();
"""

DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS trg_status_event_no_update ON publications_status_event;
DROP FUNCTION IF EXISTS prevent_append_only_mutation();
DROP TRIGGER IF EXISTS trg_version_no_update ON publications_manuscript_version;
DROP FUNCTION IF EXISTS prevent_version_mutation();
DROP TRIGGER IF EXISTS trg_manuscript_no_delete ON publications_manuscript;
DROP FUNCTION IF EXISTS prevent_manuscript_delete();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("publications", "0003_integrity_schema"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TRIGGERS, reverse_sql=DROP_TRIGGERS),
    ]
