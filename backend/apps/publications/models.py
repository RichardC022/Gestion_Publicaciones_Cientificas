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
* ``Verdict`` is the append-only editorial decision over an evaluated
  version; a correction never edits it, it adds a row that points back to
  the one it replaces (``previous_verdict``).
* ``CatalogEntry`` is the public copy of an accepted version, active at
  most once per manuscript.

The integrity layer lives in the database (TSK-31): B-tree and GIN
indexes, the generated ``search_vector`` column, the partial unique index
of the corresponding author and the triggers that reject ``DELETE`` over
manuscripts and any mutation of versions, status events and verdicts.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import connection, models
from django.db.models import F, Func, Q
from django.db.models.functions import Length
from django.db.models.lookups import Exact
from django.utils import timezone

CODE_SEQUENCE = "publications_manuscript_code_seq"

#: Length of a SHA-256 digest in hexadecimal.
SHA256_HEX_LENGTH = 64


def search_vector_expression() -> Func:
    """Full-text document of a manuscript: title, abstract and keywords.

    ``publications_search_text`` is the immutable SQL wrapper created by
    the migration; PostgreSQL only accepts immutable expressions in a
    generated column and ``array_to_string`` is not marked as such.
    """
    return Func(
        F("title"),
        F("abstract"),
        F("keywords"),
        function="to_tsvector",
        template=(
            "to_tsvector('spanish'::regconfig, "
            "publications_search_text(%(expressions)s))"
        ),
        output_field=SearchVectorField(),
    )


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


class ManuscriptQuerySet(models.QuerySet):
    """Scopes that decide which manuscripts an actor may reach at all.

    A manuscript outside the scope answers ``404`` upstream, so the
    response never reveals that it exists (plan sections 2.9 and 6.2).
    """

    def owned_by(self, user) -> "ManuscriptQuerySet":
        """Manuscripts the user registered."""
        return self.filter(created_by=user)

    def for_editor(self, user) -> "ManuscriptQuerySet":
        """Editor scope: formally submitted manuscripts without conflict.

        Drafts belong to their author until the formal submission. An
        editor who registered the manuscript or figures as author or
        coauthor has a conflict of interest and never reaches it through
        the editor role.
        """
        return (
            self.exclude(status=Manuscript.Status.DRAFT)
            .exclude(created_by=user)
            .exclude(authors__user=user)
        )

    def visible_to(self, user, *, as_author: bool, as_editor: bool) -> "ManuscriptQuerySet":
        """Union of the scopes of the roles the actor holds."""
        scopes = []
        if as_author:
            scopes.append(self.owned_by(user))
        if as_editor:
            scopes.append(self.for_editor(user))
        if not scopes:
            return self.none()
        result = scopes[0]
        for scope in scopes[1:]:
            result = result | scope
        return result


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
    # PDF de borrador reemplazable (plan 4.1): no es una versión. La ruta es
    # relativa a MEDIA_ROOT; el nombre original solo se muestra, nunca
    # construye rutas.
    draft_file_path = models.CharField(max_length=500, null=True, blank=True)
    draft_filename = models.CharField(max_length=255, null=True, blank=True)
    draft_size_bytes = models.BigIntegerField(null=True, blank=True)
    draft_uploaded_at = models.DateTimeField(null=True, blank=True)
    # Columna generada y almacenada por PostgreSQL: siempre sincronizada.
    search_vector = models.GeneratedField(
        expression=search_vector_expression(),
        output_field=SearchVectorField(),
        db_persist=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ManuscriptQuerySet.as_manager()

    class Meta:
        db_table = "publications_manuscript"
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("status", "is_active"),
                name="idx_manuscript_status_active",
            ),
            models.Index(
                fields=("created_by", "is_active"),
                name="idx_manuscript_owner_active",
            ),
            models.Index(fields=("area",), name="idx_manuscript_area"),
            GinIndex(fields=("search_vector",), name="idx_manuscript_search"),
        ]
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
            # El borrador está adjunto por completo o no lo está.
            models.CheckConstraint(
                condition=(
                    Q(
                        draft_file_path__isnull=True,
                        draft_filename__isnull=True,
                        draft_size_bytes__isnull=True,
                        draft_uploaded_at__isnull=True,
                    )
                    | Q(
                        draft_file_path__isnull=False,
                        draft_filename__isnull=False,
                        draft_size_bytes__gt=0,
                        draft_uploaded_at__isnull=False,
                    )
                ),
                name="ck_manuscript_draft_file",
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
            # Exactamente un autor responsable como máximo por manuscrito.
            models.UniqueConstraint(
                fields=("manuscript",),
                condition=Q(is_corresponding=True),
                name="uq_manuscript_corresponding",
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
        indexes = [
            models.Index(
                fields=("manuscript", "submitted_at"),
                name="idx_version_manuscript_date",
            ),
        ]
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
    ``REQUIRES_CORRECTIONS`` verdict opens the next one and keeps its
    reference in ``opened_by_verdict``. PostgreSQL creates the foreign
    key ``DEFERRABLE INITIALLY DEFERRED``, so the round and the verdict
    that opens it can be written in the same transaction in any order.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="rounds",
    )
    round_number = models.PositiveSmallIntegerField()
    # NULL en la ronda 0, que nace del envío inicial y no de un veredicto.
    opened_by_verdict = models.ForeignKey(
        "Verdict",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="opened_rounds",
    )
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
        indexes = [
            models.Index(
                fields=("manuscript", "created_at"),
                name="idx_status_event_manuscript",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.manuscript_id}: {self.from_status} → {self.to_status}"


class Verdict(AppendOnlyModel):
    """Immutable editorial decision over an evaluated version (plan section 1.15).

    ``REJECTED`` requires a justification and ``REQUIRES_CORRECTIONS``
    requires observations. In the normal flow a version has a single
    verdict; the only exception is an administrative correction, which
    adds a new row whose ``previous_verdict`` is the one it replaces and
    never updates it. The database trigger rejects ``UPDATE`` and
    ``DELETE``.
    """

    class Decision(models.TextChoices):
        ACCEPTED = "ACCEPTED", "Aceptado"
        REJECTED = "REJECTED", "Rechazado"
        REQUIRES_CORRECTIONS = "REQUIRES_CORRECTIONS", "Requiere correcciones"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="verdicts",
    )
    version = models.ForeignKey(
        ManuscriptVersion,
        on_delete=models.PROTECT,
        related_name="verdicts",
    )
    # Referencia diferida por texto: `reviews` ya depende de `publications`.
    evaluation = models.ForeignKey(
        "reviews.Evaluation",
        on_delete=models.PROTECT,
        related_name="verdicts",
    )
    editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_verdicts",
    )
    decision = models.CharField(max_length=24, choices=Decision.choices)
    justification = models.TextField(null=True, blank=True)
    observations = models.TextField(null=True, blank=True)
    # Solo una corrección administrativa enlaza con el veredicto que sustituye.
    previous_verdict = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrections",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "publications_verdict"
        ordering = ("created_at", "id")
        indexes = [
            models.Index(
                fields=("manuscript", "created_at"),
                name="idx_verdict_manuscript_date",
            ),
            models.Index(fields=("previous_verdict",), name="idx_verdict_previous"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(decision__in=("ACCEPTED", "REJECTED", "REQUIRES_CORRECTIONS")),
                name="ck_verdict_decision",
            ),
            models.CheckConstraint(
                condition=~Q(decision="REJECTED") | Q(justification__isnull=False),
                name="ck_verdict_rejected_justification",
            ),
            models.CheckConstraint(
                condition=~Q(decision="REQUIRES_CORRECTIONS") | Q(observations__isnull=False),
                name="ck_verdict_corrections_observations",
            ),
            # Un solo veredicto normal por versión; la corrección lo enlaza.
            models.UniqueConstraint(
                fields=("version",),
                condition=Q(previous_verdict__isnull=True),
                name="uq_verdict_normal_per_version",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.manuscript_id} · {self.decision}"


class CatalogEntry(models.Model):
    """Public copy of the accepted version (plan sections 1.12 and 4.7).

    ``public_file_path`` points to its own sanitized file under
    ``public/catalog``, relative to that directory: it is a copy, never a
    link to the private original, so deactivating the entry leaves the
    original intact. At most one entry is active per manuscript; the
    logical withdrawal deactivates it and sets ``unpublished_at``.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.PROTECT,
        related_name="catalog_entries",
    )
    version = models.ForeignKey(
        ManuscriptVersion,
        on_delete=models.PROTECT,
        related_name="catalog_entries",
    )
    public_file_path = models.CharField(max_length=500)
    published_at = models.DateTimeField(default=timezone.now)
    unpublished_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "publications_catalog_entry"
        ordering = ("-published_at", "id")
        constraints = [
            # Una sola entrada activa por manuscrito.
            models.UniqueConstraint(
                fields=("manuscript",),
                condition=Q(is_active=True),
                name="uq_catalog_active",
            ),
            # Activa sin fecha de retiro, o retirada con ella.
            models.CheckConstraint(
                condition=(
                    Q(is_active=True, unpublished_at__isnull=True)
                    | Q(is_active=False, unpublished_at__isnull=False)
                ),
                name="ck_catalog_unpublish",
            ),
            # La copia vive bajo `public/catalog`: nunca apunta al árbol privado.
            models.CheckConstraint(
                condition=(
                    ~Q(public_file_path="")
                    & ~Q(public_file_path__startswith="/")
                    & ~Q(public_file_path__startswith="manuscripts/")
                    & ~Q(public_file_path__contains="..")
                ),
                name="ck_catalog_public_path",
            ),
        ]

    def __str__(self) -> str:
        state = "activa" if self.is_active else "retirada"
        return f"{self.manuscript_id} · catálogo ({state})"


class IdempotencyKey(models.Model):
    """Stored answer of an idempotent ``POST`` (plan section 2.11).

    A client-chosen ``Idempotency-Key`` makes a retried request safe: the
    same key with the same request returns the stored answer without
    repeating its effects, and the same key with a different request is a
    conflict. A key belongs to one user and one endpoint, and expires 24
    hours after it was stored. Only successful answers are stored, so a
    failed attempt never consumes its key.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="idempotency_keys",
    )
    # Método y ruta de la solicitud: "POST /api/manuscripts/<uuid>/submit/".
    endpoint = models.CharField(max_length=120)
    key = models.CharField(max_length=100)
    request_hash = models.CharField(max_length=SHA256_HEX_LENGTH)
    response_status = models.SmallIntegerField()
    response_body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "publications_idempotency_key"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "endpoint", "key"),
                name="uq_idempotency_user_endpoint_key",
            ),
            models.CheckConstraint(
                condition=Q(Exact(Length("request_hash"), SHA256_HEX_LENGTH)),
                name="ck_idempotency_request_hash",
            ),
        ]
        indexes = [
            # La limpieza diaria borra por vencimiento.
            models.Index(fields=("expires_at",), name="idx_idempotency_expires"),
        ]

    def __str__(self) -> str:
        return f"{self.endpoint} · {self.key}"
