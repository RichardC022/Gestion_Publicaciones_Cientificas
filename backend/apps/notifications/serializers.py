"""Panel notice as the recipient sees it (plan section 2.8, TSK-75).

An allowlist: the event, its sanitized payload, the dates and the read
state. The manuscript is reachable only through the payload's code and
link, and no internal id, recipient or delivery detail is exposed.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ("id", "event_type", "payload", "is_read", "read_at", "created_at")
        read_only_fields = fields

    def get_is_read(self, notice: Notification) -> bool:
        return notice.read_at is not None
