"""Indexes, generated ``search_vector`` and corresponding-author index.

Plan sections 1.8-1.10 and 1.16. ``search_vector`` becomes a stored
generated column: PostgreSQL only accepts immutable expressions there and
``array_to_string`` is not marked as such, so the document is built by the
immutable SQL wrapper ``publications_search_text``. Django cannot alter a
plain column into a generated one, so the column is dropped and added
again (it carried no data). Reversible for development.
"""

from __future__ import annotations

import django.contrib.postgres.indexes
import django.contrib.postgres.search
import django.db.models.expressions
from django.db import migrations, models

CREATE_SEARCH_TEXT = """
CREATE FUNCTION publications_search_text(title text, abstract text, keywords text[])
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT title || ' ' || abstract || ' ' || array_to_string(keywords, ' ') $$;
"""

DROP_SEARCH_TEXT = "DROP FUNCTION IF EXISTS publications_search_text(text, text, text[]);"

SEARCH_VECTOR_EXPRESSION = django.db.models.expressions.Func(
    models.F("title"),
    models.F("abstract"),
    models.F("keywords"),
    function="to_tsvector",
    template=(
        "to_tsvector('spanish'::regconfig, "
        "publications_search_text(%(expressions)s))"
    ),
    output_field=django.contrib.postgres.search.SearchVectorField(),
)


class Migration(migrations.Migration):
    dependencies = [
        ("publications", "0002_manuscript_code_sequence"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_SEARCH_TEXT, reverse_sql=DROP_SEARCH_TEXT),
        migrations.RemoveField(model_name="manuscript", name="search_vector"),
        migrations.AddField(
            model_name="manuscript",
            name="search_vector",
            field=models.GeneratedField(
                expression=SEARCH_VECTOR_EXPRESSION,
                output_field=django.contrib.postgres.search.SearchVectorField(),
                db_persist=True,
            ),
        ),
        migrations.AddIndex(
            model_name="manuscript",
            index=models.Index(
                fields=["status", "is_active"],
                name="idx_manuscript_status_active",
            ),
        ),
        migrations.AddIndex(
            model_name="manuscript",
            index=models.Index(
                fields=["created_by", "is_active"],
                name="idx_manuscript_owner_active",
            ),
        ),
        migrations.AddIndex(
            model_name="manuscript",
            index=models.Index(fields=["area"], name="idx_manuscript_area"),
        ),
        migrations.AddIndex(
            model_name="manuscript",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["search_vector"],
                name="idx_manuscript_search",
            ),
        ),
        migrations.AddIndex(
            model_name="manuscriptversion",
            index=models.Index(
                fields=["manuscript", "submitted_at"],
                name="idx_version_manuscript_date",
            ),
        ),
        migrations.AddIndex(
            model_name="statusevent",
            index=models.Index(
                fields=["manuscript", "created_at"],
                name="idx_status_event_manuscript",
            ),
        ),
        migrations.AddConstraint(
            model_name="manuscriptauthor",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_corresponding=True),
                fields=("manuscript",),
                name="uq_manuscript_corresponding",
            ),
        ),
    ]
