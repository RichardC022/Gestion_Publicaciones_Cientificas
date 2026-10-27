"""Trigger that makes a final evaluation immutable (plan section 1.20).

``UPDATE`` and ``DELETE`` over a ``reviews_evaluation`` row whose stored
status is ``FINAL`` fail. The ``DRAFT`` → ``FINAL`` transition is allowed
because the check looks at the status the row had before the change, and
drafts stay editable and removable.

A ``BEFORE DELETE`` trigger that returns ``NEW`` (null in a delete) would
cancel the statement silently, so the function returns ``OLD`` for deletes.

Reversible for development.
"""

from __future__ import annotations

from django.db import migrations

CREATE_TRIGGER = """
CREATE OR REPLACE FUNCTION prevent_final_evaluation_mutation()
RETURNS trigger AS $$
BEGIN
    IF OLD.status = 'FINAL' THEN
        RAISE EXCEPTION 'La evaluación final es inmutable';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_evaluation_no_update_after_final
BEFORE UPDATE OR DELETE ON reviews_evaluation
FOR EACH ROW EXECUTE FUNCTION prevent_final_evaluation_mutation();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS trg_evaluation_no_update_after_final ON reviews_evaluation;
DROP FUNCTION IF EXISTS prevent_final_evaluation_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
