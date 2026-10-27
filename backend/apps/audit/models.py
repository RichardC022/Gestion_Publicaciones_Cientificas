"""Immutable audit trail with a SHA-256 hash chain (plan section 1.17).

``audit_audit_log`` is append-only: a database trigger rejects any
``UPDATE`` or ``DELETE`` (plan section 1.20), and every row links to the
previous one through ``previous_hash`` so tampering breaks the chain.
The table keeps only identifiers and codes: never passwords, manuscript
content or confidential comments.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    """Global append-only audit event."""

    class Result(models.TextChoices):
        SUCCESS = "SUCCESS", "Éxito"
        DENIED = "DENIED", "Denegado"
        FAILURE = "FAILURE", "Fallo"

    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Idempotencia del evento.",
    )
    occurred_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Momento exacto del evento.",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        help_text="Usuario que ejecutó la acción; NULL en eventos de sistema.",
    )
    actor_role = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Rol usado en la acción.",
    )
    action = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=40)
    entity_id = models.UUIDField(null=True, blank=True)
    result = models.CharField(max_length=16, choices=Result.choices)
    reason = models.TextField(
        null=True,
        blank=True,
        help_text="Motivo del rechazo o del fallo.",
    )
    request_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Trazabilidad de la solicitud (X-Request-ID).",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, null=True, blank=True)
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Allowlist de metadatos; nunca contenido del manuscrito.",
    )
    previous_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        editable=False,
        help_text="NULL para el primer registro de la cadena.",
    )
    entry_hash = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        db_table = "audit_audit_log"
        ordering = ("-id",)
        indexes = [
            models.Index(
                fields=("entity_type", "entity_id"),
                name="idx_audit_entity",
            ),
            models.Index(fields=("action",), name="idx_audit_action"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    result__in=("SUCCESS", "DENIED", "FAILURE")
                ),
                name="ck_audit_result",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} · {self.entity_type} · {self.result}"
