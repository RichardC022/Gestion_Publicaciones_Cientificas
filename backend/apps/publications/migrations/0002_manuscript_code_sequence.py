"""Sequence behind the ``GPC-AAAA-######`` manuscript code (plan section 1.8).

The sequence never rewinds, so a code is not reused even if the
transaction that requested it is rolled back. Reversible for development.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("publications", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE SEQUENCE publications_manuscript_code_seq START 1;",
            reverse_sql="DROP SEQUENCE IF EXISTS publications_manuscript_code_seq;",
        ),
    ]
