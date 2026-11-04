"""Database models for the notifications domain (plan section 1.18).

A ``Notification`` is one notice for one recipient on one channel. The
panel notice is available as soon as the row exists; the ``EMAIL`` ones
are delivered by ``send_pending_notifications`` (TSK-76), which tracks
``attempts``, ``last_error`` and ``next_attempt_at`` so a failing SMTP
server never blocks the panel. The service layer and the API arrive with
TSK-75.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Notification(models.Model):
    """Sanitized notice addressed to a single user."""

    class Channel(models.TextChoices):
        PANEL = "PANEL", "Panel"
        EMAIL = "EMAIL", "Correo"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        SENT = "SENT", "Enviado"
        FAILED = "FAILED", "Fallido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    # Idempotencia por evento y destinatario.
    event_key = models.CharField(max_length=120)
    event_type = models.CharField(max_length=64)
    manuscript = models.ForeignKey(
        "publications.Manuscript",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="notifications",
    )
    channel = models.CharField(max_length=16, choices=Channel.choices)
    # Contenido sanitizado, sin identidades cruzadas entre Autor y Revisor.
    payload = models.JSONField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(null=True, blank=True)
    # Backoff del reintento: NULL significa "ya puede enviarse".
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ("-created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "event_key"),
                name="uq_notification_recipient_event",
            ),
            models.CheckConstraint(
                condition=Q(channel__in=("PANEL", "EMAIL")),
                name="ck_notification_channel",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("PENDING", "SENT", "FAILED")),
                name="ck_notification_status",
            ),
        ]
        indexes = [
            models.Index(
                fields=("recipient", "read_at", "created_at"),
                name="idx_notification_inbox",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} · {self.channel} · {self.status}"
