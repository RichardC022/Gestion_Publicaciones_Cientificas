"""Domain models of manuscripts, authors, versions, rounds and events.

They follow the implementation plan (sections 1.8-1.11 and 1.16):

* ``Manuscript`` holds the current editorial state. It is never deleted
  physically: the logical withdrawal marks ``is_active=False`` together
  with ``withdrawn_at`` and keeps ``status`` untouched.
* ``ManuscriptAuthor`` stores the authors and their affiliation.
* ``ManuscriptVersion`` is the immutable record of every formal
  submission: exact PDF hashes plus a canonical snapshot of the metadata.
* ``CorrectionRound`` tracks rounds 0, 1, 2, ...
* ``StatusEvent`` is the append-only history of status transitions.

The remaining integrity layer (secondary indexes, the generated
``search_vector`` column, the partial unique index of the corresponding
author and the database triggers) belongs to the migrations of TSK-31.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.search import SearchVectorField
from django.db import connection, models
from django.db.models import Q
from django.db.models.functions import Length
from django.db.models.lookups import Exact
from django.utils import timezone

CODE_SEQUENCE = "publications_manuscript_code_seq"

#: Length of a SHA-256 digest in hexadecimal.
SHA256_HEX_LENGTH = 64


def generate_manuscript_code() -> str:
    """Build the next ``GPC-AAAA-######`` code from the PostgreSQL sequence.

    The sequence never rewinds, so a code is not reused even when the
    transaction that requested it is rolled back.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [CODE_SEQUENCE])
        (number,) = cursor.fetchone()
    return f"GPC-{timezone.localdate().year}-{number:06d}"


class AppendOnlyModel(models.Model):
    """Rows that are written once and never modified or deleted.

    The database triggers of TSK-31 are the hard barrier; this guard
    rejects the same operations earlier, at the ORM level.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError(f"{type(self).__name__} es inmutable: no admite modificaciones.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(f"{type(self).__name__} es inmutable: no admite eliminación.")


class Manuscript(models.Model):
    """Manuscript and its current editorial state."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        SUBMITTED = "SUBMITTED", "Enviado"
        UNDER_REVIEW = "UNDER_REVIEW", "En revisión"
        REQUIRES_CORRECTIONS = "REQUIRES_CORRECTIONS", "Requiere correcciones"
        ACCEPTED = "ACCEPTED", "Aceptado"
        REJECTED = "REJECTED", "Rechazado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    # Se asigna en el primer `save()` desde la secuencia de PostgreSQL.
    code = models.CharField(max_length=24, unique=True, editable=False)
    title = models.CharField(max_length=300)
    abstract = models.TextField()
    keywords = ArrayField(models.TextField())
    area = models.CharField(max_length=120)
    language = models.CharField(max_length=10)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    current_round = models.PositiveSmallIntegerField(default=0)
    current_version = models.PositiveSmallIntegerField(default=0)
    # Bloqueo optimista para `If-Match`/`ETag`.
    lock_version = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="manuscripts",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    # Borrado lógico: nunca se elimina un manuscrito.
    is_active = models.BooleanField(default=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="withdrawn_manuscripts",
    )
    withdrawal_reason = models.TextField(null=True, blank=True)
    # TSK-31 lo convierte en columna generada con su índice GIN.
    search_vector = SearchVectorField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "publications_manuscript"
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=(
                        "DRAFT",
                        "SUBMITTED",
                        "UNDER_REVIEW",
                        "REQUIRES_CORRECTIONS",
                        "ACCEPTED",
                        "REJECTED",
                    )
                ),
                name="ck_manuscript_status",
            ),
            # La baja lógica exige `is_active=false` junto con `withdrawn_at`.
            models.CheckConstraint(
                condition=(
                    Q(is_active=True, withdrawn_at__isnull=True)
                    | Q(is_active=False, withdrawn_at__isnull=False)
                ),
                name="ck_manuscript_withdrawal",
            ),
            # `GPC-AAAA-######`; el contador admite hasta dos dígitos más.
            models.CheckConstraint(
                condition=Q(code__regex=r"^GPC-[0-9]{4}-[0-9]{6,8}$"),
                name="ck_manuscript_code_format",
            ),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and not self.code:
            self.code = generate_manuscript_code()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} · {self.title}"


class ManuscriptAuthor(models.Model):
    """Author of a manuscript with affiliation and contact."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="authors",
    )
    # Vincula al autor con su cuenta cuando existe.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authorships",
    )
    full_name = models.CharField(max_length=200)
    email = models.EmailField(max_length=254)
    affiliation = models.CharField(max_length=300)
    is_corresponding = models.BooleanField(default=False)
    author_order = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "publications_manuscript_author"
        ordering = ("author_order",)
        constraints = [
            models.UniqueConstraint(
                fields=("manuscript", "author_order"),
                name="uq_author_manuscript_order",
            ),
            models.UniqueConstraint(
                fields=("manuscript", "email"),
                name="uq_author_manuscript_email",
            ),
            models.CheckConstraint(
                condition=Q(author_order__gt=0),
                name="ck_author_order_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.manuscript_id})"


class ManuscriptVersion(AppendOnlyModel):
    """Immutable formal submission: exact PDF, hashes and metadata snapshot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="versions",
    )
    version_number = models.PositiveSmallIntegerField()
    round_number = models.PositiveSmallIntegerField()
    # Ruta relativa al volumen privado; solo UUID y versión, nunca el título.
    original_file_path = models.CharField(max_length=500)
    # Solo para Autor y Editor, nunca para el Revisor.
    original_filename = models.CharField(max_length=255)
    original_size_bytes = models.BigIntegerField()
    original_sha256 = models.CharField(max_length=SHA256_HEX_LENGTH)
    sanitized_file_path = models.CharField(max_length=500)
    sanitized_sha256 = models.CharField(max_length=SHA256_HEX_LENGTH)
    # Copia exacta de metadatos y autores al momento del envío.
    metadata_snapshot = models.JSONField()
    metadata_sha256 = models.CharField(max_length=SHA256_HEX_LENGTH)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_versions",
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "publications_manuscript_version"
        ordering = ("version_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("manuscript", "version_number"),
                name="uq_version_manuscript_number",
            ),
            models.CheckConstraint(
                condition=Q(version_number__gt=0),
                name="ck_version_number_positive",
            ),
            models.CheckConstraint(
                condition=Q(original_size_bytes__gt=0),
                name="ck_version_size_positive",
            ),
            models.CheckConstraint(
                condition=Q(Exact(Length("original_sha256"), SHA256_HEX_LENGTH)),
                name="ck_version_original_sha256",
            ),
            models.CheckConstraint(
                condition=Q(Exact(Length("sanitized_sha256"), SHA256_HEX_LENGTH)),
                name="ck_version_sanitized_sha256",
            ),
            models.CheckConstraint(
                condition=Q(Exact(Length("metadata_sha256"), SHA256_HEX_LENGTH)),
                name="ck_version_metadata_sha256",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.manuscript_id} · v{self.version_number}"


class CorrectionRound(models.Model):
    """Review round 0, 1, 2, ... of a manuscript.

    Round 0 opens with the first submission and closes with v1; each
    ``REQUIRES_CORRECTIONS`` verdict opens the next one. The reference to
    the verdict that opened it is added with the verdict model (TSK-50).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="rounds",
    )
    round_number = models.PositiveSmallIntegerField()
    opened_at = models.DateTimeField(default=timezone.now)
    closed_by_version = models.ForeignKey(
        ManuscriptVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="closed_rounds",
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "publications_correction_round"
        ordering = ("round_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("manuscript", "round_number"),
                name="uq_round_manuscript_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.manuscript_id} · ronda {self.round_number}"


class StatusEvent(AppendOnlyModel):
    """Append-only record of one status transition."""

    id = models.BigAutoField(primary_key=True)
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="status_events",
    )
    # NULL en el evento inicial.
    from_status = models.CharField(max_length=24, null=True, blank=True)
    to_status = models.CharField(max_length=24)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_events",
    )
    reason = models.TextField(null=True, blank=True)
    # Sin contenido del manuscrito.
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "publications_status_event"
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"{self.manuscript_id}: {self.from_status} → {self.to_status}"
