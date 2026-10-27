"""Trigger that makes verdicts append-only (plan section 1.20).

``UPDATE`` and ``DELETE`` over ``publications_verdict`` fail through the
generic ``prevent_append_only_mutation`` function created in ``0004``,
the same one that protects the status events. A correction adds a row;
it never edits the original verdict.

Reversible for development.
"""

from __future__ import annotations

from django.db import migrations

CREATE_TRIGGER = """
CREATE TRIGGER trg_verdict_no_update
BEFORE UPDATE OR DELETE ON publications_verdict
FOR EACH ROW EXECUTE FUNCTION prevent_append_only_mutation();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS trg_verdict_no_update ON publications_verdict;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("publications", "0007_verdict_catalog_entry"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
