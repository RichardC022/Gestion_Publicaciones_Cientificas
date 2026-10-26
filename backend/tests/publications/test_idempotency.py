"""Tests for the idempotency of the POST operations (TSK-39).

Covers the acceptance criteria:

1. The same key with the same request returns the same answer without
   repeating any effect.
2. The same key with a different request answers ``409``.
3. Expired keys are deleted without touching the live ones.

Plus the contracts of the plan (section 2.11): a 24-hour life, one key
per user and endpoint, a key that a failed attempt does not consume, and
duplicates that arrive at the same time.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.publications.models import (
    CorrectionRound,
    IdempotencyKey,
    Manuscript,
    ManuscriptVersion,
    StatusEvent,
)
from apps.publications.services.idempotency import (
    IDEMPOTENCY_TTL,
    KEY_REUSED_MESSAGE,
    IdempotencyScope,
    IdempotentReplay,
    delete_expired_keys,
    request_hash,
)
from apps.publications.services.submission import submit_manuscript
from apps.publications.signals import manuscript_submitted, new_version_submitted
from config.exceptions import DomainError
from tests.publications import pdf_factory as factory
from tests.publications.test_draft_file import draft_url, pdf_file
from tests.publications.test_manuscript_api import (  # noqa: F401
    actor,
    client_for,
    detail_url,
    error_code,
)
from tests.publications.test_new_version import (  # noqa: F401
    CORRECTED_PDF,
    ORIGINAL_PDF,
    corrected,
    request_corrections,
    send,
    versions_url,
)
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    owner,
    ready_draft,
    seeded_roles,
    submit,
    submit_url,
    version_dir_of,
)

pytestmark = pytest.mark.django_db

CONTEXT = {"request_id": "r-1", "ip_address": None, "user_agent": None}


def stored_rows(user=None):
    rows = IdempotencyKey.objects.all()
    return rows.filter(user=user) if user else rows


def version_rows():
    """Keys stored by the new-version endpoint (the fixtures also store a submit key)."""
    return IdempotencyKey.objects.filter(endpoint__endswith="/versions/")


def make_scope(user, key="clave-unica", endpoint="POST /api/test/", digest="payload-1"):
    return IdempotencyScope(
        user=user,
        endpoint=endpoint,
        key=key,
        request_hash=lambda: request_hash(digest),
        render=lambda result: (201, {"code": result.manuscript.code}),
    )


def seed_key(user, *, key="k", endpoint="POST /api/test/", expires_in=timedelta(hours=1), digest="d"):
    return IdempotencyKey.objects.create(
        user=user,
        endpoint=endpoint,
        key=key,
        request_hash=request_hash(digest),
        response_status=201,
        response_body={"ok": True},
        expires_at=timezone.now() + expires_in,
    )


class TestRequestHash:
    def test_it_is_a_sha256_and_deterministic(self) -> None:
        assert request_hash("a", {"b": 1}) == request_hash("a", {"b": 1})
        assert len(request_hash("a")) == 64

    def test_key_order_inside_a_part_does_not_matter(self) -> None:
        assert request_hash({"x": 1, "y": 2}) == request_hash({"y": 2, "x": 1})

    def test_a_different_part_or_order_changes_it(self) -> None:
        assert request_hash("a", "b") != request_hash("b", "a")
        assert request_hash("a") != request_hash("a", "b")


class TestStoredKeyModel:
    def test_a_key_is_unique_per_user_and_endpoint(self, owner) -> None:
        seed_key(owner)

        with pytest.raises(IntegrityError), transaction.atomic():
            seed_key(owner)

    def test_the_same_key_is_independent_across_users_and_endpoints(self, owner) -> None:
        other = actor("AUTHOR")

        seed_key(owner)
        seed_key(other)
        seed_key(owner, endpoint="POST /api/other/")

        assert stored_rows().count() == 3

    def test_the_request_hash_must_be_64_characters(self, owner) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            IdempotencyKey.objects.create(
                user=owner, endpoint="POST /x/", key="k", request_hash="corto",
                response_status=201, response_body={}, expires_at=timezone.now(),
            )


class TestScope:
    def test_nothing_is_found_for_an_unknown_key(self, owner) -> None:
        assert make_scope(owner).find() is None

    def test_a_live_key_with_the_same_request_returns_the_stored_answer(self, owner) -> None:
        seed_key(owner, key="k", digest="payload-1")

        stored = make_scope(owner, key="k", digest="payload-1").find()

        assert (stored.status, stored.body) == (201, {"ok": True})

    def test_the_same_key_with_another_request_is_a_409(self, owner) -> None:
        seed_key(owner, key="k", digest="payload-1")

        with pytest.raises(DomainError) as raised:
            make_scope(owner, key="k", digest="payload-2").find()

        assert raised.value.status_code == 409
        assert str(raised.value.detail) == KEY_REUSED_MESSAGE
        assert raised.value.error_details == {"idempotency": "KEY_REUSED_WITH_DIFFERENT_REQUEST"}

    def test_the_hash_is_only_computed_when_a_key_exists(self, owner) -> None:
        calls = []
        scope = IdempotencyScope(
            user=owner, endpoint="POST /api/test/", key="k",
            request_hash=lambda: calls.append(1) or "x" * 64,
            render=lambda result: (201, {}),
        )

        assert scope.find() is None and calls == []

    def test_keys_never_cross_users_or_endpoints(self, owner) -> None:
        seed_key(owner, key="k", endpoint="POST /api/a/")

        assert make_scope(actor("AUTHOR"), key="k", endpoint="POST /api/a/").find() is None
        assert make_scope(owner, key="k", endpoint="POST /api/b/").find() is None

    def test_an_expired_key_is_ignored_by_find(self, owner) -> None:
        seed_key(owner, key="k", expires_in=timedelta(seconds=-1))

        assert make_scope(owner, key="k").find() is None

    def test_inside_the_transaction_an_expired_key_is_forgotten_and_replaced(self, owner) -> None:
        seed_key(owner, key="k", expires_in=timedelta(seconds=-1), digest="viejo")

        with transaction.atomic():
            assert make_scope(owner, key="k", digest="nuevo").lock_and_find() is None

        assert stored_rows(owner).count() == 0


class TestExpiry:
    def test_a_stored_key_lives_exactly_24_hours(self, owner) -> None:
        assert IDEMPOTENCY_TTL == timedelta(hours=24)
        before = timezone.now()

        class Result:
            class manuscript:
                code = "GPC-2026-000001"

        make_scope(owner).store_result(Result)

        [row] = stored_rows(owner)
        assert before + IDEMPOTENCY_TTL <= row.expires_at <= timezone.now() + IDEMPOTENCY_TTL
        assert row.response_status == 201 and row.response_body == {"code": "GPC-2026-000001"}

    def test_cleanup_removes_expired_keys_and_never_touches_live_ones(self, owner) -> None:
        seed_key(owner, key="vencida-1", expires_in=timedelta(hours=-5))
        seed_key(owner, key="vencida-2", expires_in=timedelta(seconds=-1))
        live = seed_key(owner, key="vigente-1", expires_in=timedelta(hours=1))
        later = seed_key(owner, key="vigente-2", expires_in=timedelta(hours=23, minutes=59))

        deleted = delete_expired_keys()

        assert deleted == 2
        assert set(stored_rows().values_list("pk", flat=True)) == {live.pk, later.pk}

    def test_a_key_is_expired_at_the_exact_instant(self, owner) -> None:
        moment = timezone.now()
        IdempotencyKey.objects.create(
            user=owner, endpoint="POST /x/", key="justo", request_hash=request_hash("d"),
            response_status=201, response_body={}, expires_at=moment,
        )
        IdempotencyKey.objects.create(
            user=owner, endpoint="POST /x/", key="despues", request_hash=request_hash("d"),
            response_status=201, response_body={}, expires_at=moment + timedelta(microseconds=1),
        )

        assert delete_expired_keys(now=moment) == 1
        assert list(stored_rows().values_list("key", flat=True)) == ["despues"]

    def test_cleanup_with_nothing_expired_deletes_nothing(self, owner) -> None:
        seed_key(owner, expires_in=timedelta(hours=1))

        assert delete_expired_keys() == 0 and stored_rows().count() == 1


class TestSubmitIdempotency:
    def test_the_same_key_replays_the_same_answer_without_repeating_effects(self, owner, submit) -> None:
        manuscript = ready_draft(owner)

        first = submit(owner, manuscript, key="envio-1")
        second = submit(owner, manuscript, key="envio-1")

        assert first.status_code == second.status_code == 201
        assert second.json() == first.json()
        assert "Idempotent-Replayed" not in first.headers
        assert second["Idempotent-Replayed"] == "true"
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1
        assert CorrectionRound.objects.filter(manuscript=manuscript).count() == 1
        assert StatusEvent.objects.filter(manuscript=manuscript).count() == 2
        assert AuditLog.objects.filter(action="MANUSCRIPT_SUBMITTED").count() == 1
        manuscript.refresh_from_db()
        assert manuscript.lock_version == 1

    def test_the_answer_is_stored_with_its_key_endpoint_hash_and_expiry(self, owner, submit) -> None:
        manuscript = ready_draft(owner)

        first = submit(owner, manuscript, key="envio-1")

        [row] = stored_rows(owner)
        assert row.key == "envio-1" and row.endpoint == f"POST /api/manuscripts/{manuscript.pk}/submit/"
        assert row.response_status == 201 and row.response_body == first.json()
        assert row.request_hash == request_hash(str(manuscript.pk))
        assert abs((row.expires_at - row.created_at) - IDEMPOTENCY_TTL) < timedelta(seconds=5)

    def test_a_replay_does_not_announce_the_submission_again(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        received = []

        def listener(sender, **kwargs):
            received.append(kwargs)

        manuscript_submitted.connect(listener, dispatch_uid="idem-submit")
        try:
            submit(owner, manuscript, key="envio-1")
            submit(owner, manuscript, key="envio-1")
        finally:
            manuscript_submitted.disconnect(dispatch_uid="idem-submit")

        assert len(received) == 1

    def test_the_stored_answer_is_served_even_after_the_manuscript_moved_on(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        first = submit(owner, manuscript, key="envio-1")
        Manuscript.objects.filter(pk=manuscript.pk).update(status="UNDER_REVIEW")

        replay = submit(owner, manuscript, key="envio-1")

        assert replay.status_code == 201 and replay.json() == first.json()

    def test_a_new_key_on_a_submitted_manuscript_is_still_a_409(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        submit(owner, manuscript, key="envio-1")

        again = submit(owner, manuscript, key="envio-2")

        assert again.status_code == 409 and error_code(again) == "STATE_CONFLICT"
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1

    def test_the_key_is_mandatory_for_the_submission(self, owner) -> None:
        manuscript = ready_draft(owner)

        response = client_for(owner).post(submit_url(manuscript), format="json")

        assert response.status_code == 400 and "Idempotency-Key" in response.json()["error"]["message"]
        assert not ManuscriptVersion.objects.exists() and stored_rows().count() == 0

    @pytest.mark.parametrize("key", ["   ", "clave con espacios", "ñandú", "x" * 101])
    def test_a_malformed_key_is_rejected(self, owner, key) -> None:
        manuscript = ready_draft(owner)

        response = client_for(owner).post(submit_url(manuscript), format="json", HTTP_IDEMPOTENCY_KEY=key)

        assert response.status_code == 400
        assert not ManuscriptVersion.objects.exists()

    def test_a_missing_key_on_an_already_submitted_manuscript_still_answers_409_first(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        submit(owner, manuscript)

        response = client_for(owner).post(submit_url(manuscript), format="json")

        assert response.status_code == 409

    def test_the_same_key_on_two_manuscripts_is_two_independent_operations(self, owner, submit) -> None:
        first, second = ready_draft(owner), ready_draft(owner)

        a = submit(owner, first, key="compartida")
        b = submit(owner, second, key="compartida")

        assert a.status_code == b.status_code == 201 and a.json()["code"] != b.json()["code"]
        assert stored_rows(owner).count() == 2

    def test_a_failed_attempt_does_not_consume_the_key(self, owner, submit, monkeypatch) -> None:
        manuscript = ready_draft(owner)

        def fail(**kwargs):
            raise AuditUnavailable("sin auditoría")

        with monkeypatch.context() as patched:
            patched.setattr(AuditService, "record", staticmethod(fail))
            failed = submit(owner, manuscript, key="reintento")
        assert failed.status_code == 503
        assert stored_rows().count() == 0

        retry = submit(owner, manuscript, key="reintento")

        assert retry.status_code == 201 and "Idempotent-Replayed" not in retry.headers
        assert stored_rows(owner).count() == 1

    def test_a_validation_failure_does_not_consume_the_key_either(self, owner, submit) -> None:
        created = client_for(owner).post(
            "/api/manuscripts/",
            {"authors": [{
                "full_name": owner.get_full_name(), "email": owner.email,
                "affiliation": "UNL", "is_corresponding": True,
            }]},
            format="json",
        ).json()
        manuscript = Manuscript.objects.get(pk=created["id"])
        assert submit(owner, manuscript, key="completar").status_code == 400
        assert stored_rows().count() == 0

        client_for(owner).patch(
            detail_url(manuscript),
            {"title": "T", "abstract": "A", "keywords": ["k"], "area": "X", "language": "es"},
            format="json", HTTP_IF_MATCH='"0"',
        )
        uploaded = client_for(owner).post(
            draft_url(manuscript), {"file": pdf_file()}, format="multipart"
        )
        assert uploaded.status_code == 201

        assert submit(owner, manuscript, key="completar").status_code == 201

    def test_another_user_cannot_replay_somebody_elses_key(self, owner, submit) -> None:
        manuscript = ready_draft(owner)
        submit(owner, manuscript, key="envio-1")

        stranger = submit(actor("AUTHOR"), manuscript, key="envio-1")

        assert stranger.status_code == 404
        assert "Idempotent-Replayed" not in stranger.headers


class TestSubmitKeyExpiry:
    def test_the_answer_is_replayed_until_24_hours_and_forgotten_after(self, owner, django_capture_on_commit_callbacks) -> None:
        manuscript = ready_draft(owner)
        start = timezone.now()

        def post(key="envio-1"):
            with django_capture_on_commit_callbacks(execute=True):
                return client_for(owner).post(
                    submit_url(manuscript), format="json", HTTP_IDEMPOTENCY_KEY=key
                )

        with freeze_time(start) as clock:
            first = post()
            clock.move_to(start + timedelta(hours=23, minutes=59, seconds=59))
            inside = post()
            clock.move_to(start + IDEMPOTENCY_TTL)
            after = post()

        assert first.status_code == 201
        assert inside.status_code == 201 and inside["Idempotent-Replayed"] == "true"
        assert after.status_code == 409 and "Idempotent-Replayed" not in after.headers
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1


class TestServiceLevelReplay:
    def run(self, owner, manuscript, scope, key="envio-1"):
        return submit_manuscript(
            manuscript_id=manuscript.pk, user=owner, idempotency_key=key,
            context=CONTEXT, idempotency=scope,
        )

    def scope(self, owner, manuscript, digest=None):
        return IdempotencyScope(
            user=owner,
            endpoint=f"POST /api/manuscripts/{manuscript.pk}/submit/",
            key="envio-1",
            request_hash=lambda: request_hash(digest or str(manuscript.pk)),
            render=lambda result: (201, {"code": result.manuscript.code}),
        )

    def test_a_duplicate_that_reaches_the_transaction_replays_instead_of_failing(self, owner) -> None:
        manuscript = ready_draft(owner)
        self.run(owner, manuscript, self.scope(owner, manuscript))

        with pytest.raises(IdempotentReplay) as replay:
            self.run(owner, manuscript, self.scope(owner, manuscript))

        assert replay.value.stored.status == 201
        assert replay.value.stored.body == {"code": manuscript.code}
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1

    def test_a_different_request_under_the_same_key_conflicts_inside_the_transaction(self, owner) -> None:
        manuscript = ready_draft(owner)
        self.run(owner, manuscript, self.scope(owner, manuscript))

        with pytest.raises(DomainError) as raised:
            self.run(owner, manuscript, self.scope(owner, manuscript, digest="otra-solicitud"))

        assert raised.value.status_code == 409

    def test_an_expired_key_is_replaced_and_the_operation_runs_again(self, owner) -> None:
        manuscript = ready_draft(owner)
        stale = IdempotencyKey.objects.create(
            user=owner, endpoint=f"POST /api/manuscripts/{manuscript.pk}/submit/", key="envio-1",
            request_hash=request_hash("viejo"), response_status=201, response_body={"viejo": True},
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        result = self.run(owner, manuscript, self.scope(owner, manuscript))

        assert result.version.version_number == 1
        [row] = stored_rows(owner)
        assert row.pk != stale.pk and row.response_body == {"code": manuscript.code}
        assert row.expires_at > timezone.now()

    def test_the_key_and_its_effect_commit_or_roll_back_together(self, owner, media_root, monkeypatch) -> None:
        manuscript = ready_draft(owner)
        scope = self.scope(owner, manuscript)

        def fail(result):
            raise RuntimeError("no se pudo guardar la clave")

        monkeypatch.setattr(scope, "render", fail)
        with pytest.raises(RuntimeError):
            self.run(owner, manuscript, scope)

        manuscript.refresh_from_db()
        assert manuscript.status == "DRAFT"
        assert not ManuscriptVersion.objects.exists() and stored_rows().count() == 0
        assert not version_dir_of(media_root, manuscript).exists()


class TestVersionIdempotency:
    def test_the_same_key_and_pdf_replay_the_same_answer_without_repeating_effects(self, owner, corrected, send, media_root) -> None:
        first = send(owner, corrected, key="version-1")
        second = send(owner, corrected, key="version-1")

        assert first.status_code == second.status_code == 201
        assert second.json() == first.json()
        assert second["Idempotent-Replayed"] == "true" and "Idempotent-Replayed" not in first.headers
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 2
        assert CorrectionRound.objects.filter(manuscript=corrected).count() == 2
        assert AuditLog.objects.filter(action="MANUSCRIPT_VERSION_SUBMITTED").count() == 1
        assert not version_dir_of(media_root, corrected, 3).exists()
        assert list((media_root / "tmp" / "uploads").glob("*")) == []

    def test_the_file_name_is_not_part_of_the_request_identity(self, owner, corrected, send) -> None:
        first = send(owner, corrected, pdf_file(CORRECTED_PDF, name="uno.pdf"), key="version-1")
        second = send(owner, corrected, pdf_file(CORRECTED_PDF, name="otro-nombre.pdf"), key="version-1")

        assert second.status_code == 201 and second.json() == first.json()
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 2

    def test_the_same_key_with_another_pdf_is_a_409_and_creates_nothing(self, owner, corrected, send) -> None:
        send(owner, corrected, key="version-1")

        conflict = send(owner, corrected, pdf_file(factory.clean_pdf(pages=4)), key="version-1")

        assert conflict.status_code == 409 and error_code(conflict) == "STATE_CONFLICT"
        assert conflict.json()["error"]["message"] == KEY_REUSED_MESSAGE
        assert conflict.json()["error"]["details"] == {"idempotency": "KEY_REUSED_WITH_DIFFERENT_REQUEST"}
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 2

    def test_the_stored_row_identifies_the_pdf_by_its_hash(self, owner, corrected, send) -> None:
        from apps.publications.services.pdf import sha256_of_chunks

        send(owner, corrected, key="version-1")

        [row] = stored_rows(owner).filter(key="version-1")
        assert row.endpoint == f"POST /api/manuscripts/{corrected.pk}/versions/"
        assert row.request_hash == request_hash(str(corrected.pk), sha256_of_chunks([CORRECTED_PDF]))

    def test_a_replay_does_not_announce_the_version_again(self, owner, corrected, send) -> None:
        received = []

        def listener(sender, **kwargs):
            received.append(kwargs)

        new_version_submitted.connect(listener, dispatch_uid="idem-version")
        try:
            send(owner, corrected, key="version-1")
            send(owner, corrected, key="version-1")
        finally:
            new_version_submitted.disconnect(dispatch_uid="idem-version")

        assert len(received) == 1

    def test_a_rejected_submission_without_changes_does_not_consume_the_key(self, owner, corrected, send) -> None:
        unchanged = send(owner, corrected, pdf_file(ORIGINAL_PDF), key="version-1")
        assert unchanged.status_code == 400 and version_rows().count() == 0

        corrected_pdf = send(owner, corrected, pdf_file(CORRECTED_PDF), key="version-1")

        assert corrected_pdf.status_code == 201 and "Idempotent-Replayed" not in corrected_pdf.headers

    def test_an_invalid_pdf_does_not_consume_the_key(self, owner, corrected, send) -> None:
        assert send(owner, corrected, pdf_file(b"no es un pdf"), key="version-1").status_code == 400
        assert version_rows().count() == 0

        assert send(owner, corrected, key="version-1").status_code == 201

    def test_a_new_key_after_success_is_a_409_not_a_second_version(self, owner, corrected, send) -> None:
        send(owner, corrected, key="version-1")

        again = send(owner, corrected, key="version-2")

        assert again.status_code == 409
        assert ManuscriptVersion.objects.filter(manuscript=corrected).count() == 2

    def test_the_key_expires_after_24_hours(self, owner, corrected, django_capture_on_commit_callbacks) -> None:
        start = timezone.now()

        def post():
            with django_capture_on_commit_callbacks(execute=True):
                return client_for(owner).post(
                    versions_url(corrected),
                    {"file": pdf_file(CORRECTED_PDF)},
                    format="multipart",
                    HTTP_IDEMPOTENCY_KEY="version-1",
                )

        with freeze_time(start) as clock:
            first = post()
            clock.move_to(start + timedelta(hours=23))
            inside = post()
            clock.move_to(start + IDEMPOTENCY_TTL + timedelta(seconds=1))
            after = post()

        assert first.status_code == 201
        assert inside["Idempotent-Replayed"] == "true"
        assert after.status_code == 409 and "Idempotent-Replayed" not in after.headers


@pytest.mark.django_db(transaction=True)
class TestConcurrentDuplicates:
    """Real parallel requests: each thread has its own database connection."""

    def fire(self, owner, url, key, *, how_many=3):
        barrier = threading.Barrier(how_many)

        def call(_):
            try:
                client = APIClient()
                client.force_authenticate(owner)
                barrier.wait(timeout=10)
                response = client.post(url, format="json", HTTP_IDEMPOTENCY_KEY=key)
                return response.status_code, response.json(), response.headers.get("Idempotent-Replayed")
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=how_many) as pool:
            return list(pool.map(call, range(how_many)))

    def test_simultaneous_duplicates_create_one_version_and_all_get_the_same_answer(self, owner) -> None:
        manuscript = ready_draft(owner)

        results = self.fire(owner, submit_url(manuscript), "carrera-1")

        assert [status for status, _, _ in results] == [201, 201, 201]
        assert all(body == results[0][1] for _, body, _ in results)
        assert sum(1 for _, _, replayed in results if replayed is None) == 1
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1
        assert CorrectionRound.objects.filter(manuscript=manuscript).count() == 1
        assert AuditLog.objects.filter(action="MANUSCRIPT_SUBMITTED").count() == 1
        assert IdempotencyKey.objects.filter(user=owner).count() == 1

    def test_simultaneous_requests_with_different_keys_register_only_one_submission(self, owner) -> None:
        manuscript = ready_draft(owner)
        barrier = threading.Barrier(3)

        def call(index):
            try:
                client = APIClient()
                client.force_authenticate(owner)
                barrier.wait(timeout=10)
                return client.post(
                    submit_url(manuscript), format="json", HTTP_IDEMPOTENCY_KEY=f"clave-{index}"
                ).status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=3) as pool:
            statuses = sorted(pool.map(call, range(3)))

        assert statuses == [201, 409, 409]
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 1
