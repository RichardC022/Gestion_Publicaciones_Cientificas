"""Real concurrency on the manuscript module (TSK-40).

The tests of the plan (section 7.1) ask for transaction and concurrency
cases "con dos conexiones". Here the requests run in parallel threads,
each with its own database connection, released together by a barrier.
They check the guarantees the row lock and the unique constraints give:

* two simultaneous new versions register only the next one (CA-HU-09-06)
  and never overwrite files;
* two simultaneous edits with the same ``ETag`` keep a single winner
  (CA-HU-07-05);
* a withdrawal racing a submission or an upload never leaves a partial
  version or an orphan file (CA-HU-08-08).

Whatever the order the threads happen to take, the invariants must hold.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.publications.models import (
    CorrectionRound,
    IdempotencyKey,
    Manuscript,
    ManuscriptVersion,
    StatusEvent,
)
from apps.publications.services.pdf import sha256_of_file
from tests.publications import pdf_factory as factory
from tests.publications.test_draft_file import draft_url, pdf_file
from tests.publications.test_lifecycle import assert_audit_chain_intact, tree_digest
from tests.publications.test_manuscript_api import (  # noqa: F401
    URL,
    actor,
    client_for,
    create_payload,
    detail_url,
    error_code,
)
from tests.publications.test_new_version import request_corrections, versions_url
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    owner,
    ready_draft,
    seeded_roles,
    submit,
    submit_url,
    version_dir_of,
)
from tests.publications.test_withdraw import withdraw_url

pytestmark = pytest.mark.django_db(transaction=True)


def parallel(user, calls: list[Callable[[APIClient], object]]) -> list:
    """Run every call at the same time, each with its own client and connection."""
    barrier = threading.Barrier(len(calls))

    def run(call):
        try:
            client = APIClient(raise_request_exception=False)
            client.force_authenticate(user)
            barrier.wait(timeout=15)
            return call(client)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


def statuses(responses) -> list[int]:
    return sorted(response.status_code for response in responses)


def drafts_on_disk(media_root) -> list:
    return sorted((media_root / "private" / "drafts").rglob("*.pdf"))


class TestSimultaneousNewVersions:
    @pytest.fixture
    def awaiting(self, owner, submit):
        manuscript = ready_draft(owner, pdf=factory.clean_pdf(pages=1))
        assert submit(owner, manuscript).status_code == 201
        request_corrections(manuscript)
        return manuscript

    def test_only_the_next_version_is_registered_and_files_are_not_overwritten(
        self, owner, awaiting, media_root
    ) -> None:
        candidates = {pages: factory.clean_pdf(pages=pages) for pages in (2, 3, 4)}
        v1_files = tree_digest(version_dir_of(media_root, awaiting, 1))

        def post(pages):
            return lambda client: client.post(
                versions_url(awaiting),
                {"file": pdf_file(candidates[pages], name=f"v-{pages}.pdf")},
                format="multipart",
                HTTP_IDEMPOTENCY_KEY=f"carrera-{pages}",
            )

        responses = parallel(owner, [post(2), post(3), post(4)])

        assert statuses(responses) == [201, 409, 409]
        for loser in (r for r in responses if r.status_code == 409):
            assert error_code(loser) == "STATE_CONFLICT"
        assert ManuscriptVersion.objects.filter(manuscript=awaiting).count() == 2
        winner = ManuscriptVersion.objects.get(manuscript=awaiting, version_number=2)
        directory = version_dir_of(media_root, awaiting, 2)
        assert sha256_of_file(directory / "original.pdf") == winner.original_sha256
        assert winner.original_sha256 in {hashlib.sha256(d).hexdigest() for d in candidates.values()}
        assert sha256_of_file(directory / "sanitized.pdf") == winner.sanitized_sha256
        assert not version_dir_of(media_root, awaiting, 3).exists()
        assert tree_digest(version_dir_of(media_root, awaiting, 1)) == v1_files

        awaiting.refresh_from_db()
        assert (awaiting.status, awaiting.current_version) == ("SUBMITTED", 2)
        assert CorrectionRound.objects.get(manuscript=awaiting, round_number=1).closed_by_version == winner
        assert AuditLog.objects.filter(action="MANUSCRIPT_VERSION_SUBMITTED", result="SUCCESS").count() == 1
        assert IdempotencyKey.objects.filter(endpoint__endswith="/versions/").count() == 1
        assert list((media_root / "tmp" / "uploads").glob("*")) == []
        assert_audit_chain_intact()

    def test_the_same_pdf_with_different_keys_still_registers_a_single_version(
        self, owner, awaiting, media_root
    ) -> None:
        data = factory.clean_pdf(pages=2)

        def post(index):
            return lambda client: client.post(
                versions_url(awaiting),
                {"file": pdf_file(data)},
                format="multipart",
                HTTP_IDEMPOTENCY_KEY=f"misma-carga-{index}",
            )

        responses = parallel(owner, [post(i) for i in range(3)])

        assert statuses(responses) == [201, 409, 409]
        assert ManuscriptVersion.objects.filter(manuscript=awaiting).count() == 2
        assert not version_dir_of(media_root, awaiting, 3).exists()


class TestSimultaneousEdits:
    def test_a_single_edit_wins_when_everyone_sends_the_same_etag(self, owner) -> None:
        created = client_for(owner).post(URL, create_payload(owner), format="json").json()
        manuscript = Manuscript.objects.get(pk=created["id"])

        def patch(index):
            return lambda client: client.patch(
                detail_url(manuscript),
                {"title": f"Título del hilo {index}"},
                format="json",
                HTTP_IF_MATCH='"0"',
            )

        responses = parallel(owner, [patch(i) for i in range(4)])

        assert statuses(responses) == [200, 409, 409, 409]
        for loser in (r for r in responses if r.status_code == 409):
            assert error_code(loser) == "VERSION_CONFLICT"
        winner = next(r for r in responses if r.status_code == 200)
        manuscript.refresh_from_db()
        assert manuscript.title == winner.json()["title"] and manuscript.lock_version == 1
        assert AuditLog.objects.filter(action="MANUSCRIPT_UPDATED").count() == 1

    def test_the_author_list_is_replaced_atomically_under_concurrent_edits(self, owner) -> None:
        created = client_for(owner).post(URL, create_payload(owner), format="json").json()
        manuscript = Manuscript.objects.get(pk=created["id"])
        registrant = create_payload(owner)["authors"][0]

        def patch(index):
            authors = [registrant, {
                "full_name": f"Coautor {index}", "email": f"co{index}@otra.edu",
                "affiliation": "Otra U", "is_corresponding": False,
            }]
            return lambda client: client.patch(
                detail_url(manuscript), {"authors": authors}, format="json", HTTP_IF_MATCH='"0"'
            )

        responses = parallel(owner, [patch(i) for i in range(3)])

        assert statuses(responses) == [200, 409, 409]
        emails = list(manuscript.authors.order_by("author_order").values_list("email", flat=True))
        assert len(emails) == 2 and emails[0] == owner.email and emails[1].startswith("co")
        assert manuscript.authors.filter(is_corresponding=True).count() == 1


class TestSimultaneousWithdrawals:
    def test_only_one_withdrawal_is_recorded(self, owner) -> None:
        manuscript = ready_draft(owner)

        def withdraw(client):
            return client.post(withdraw_url(manuscript), {"reason": "Retiro."}, format="json")

        responses = parallel(owner, [withdraw] * 3)

        assert statuses(responses) == [200, 409, 409]
        manuscript.refresh_from_db()
        assert manuscript.is_active is False and manuscript.lock_version == 1
        assert StatusEvent.objects.filter(manuscript=manuscript, metadata__withdrawn=True).count() == 1
        assert AuditLog.objects.filter(action="MANUSCRIPT_WITHDRAWN").count() == 1


class TestSimultaneousDraftUploads:
    def test_one_draft_file_survives_and_matches_the_database(self, owner, media_root) -> None:
        created = client_for(owner).post(URL, create_payload(owner), format="json").json()
        manuscript = Manuscript.objects.get(pk=created["id"])
        files = {f"carga-{pages}.pdf": factory.clean_pdf(pages=pages) for pages in (1, 2, 3)}

        def upload(name):
            return lambda client: client.post(
                draft_url(manuscript), {"file": pdf_file(files[name], name=name)}, format="multipart"
            )

        responses = parallel(owner, [upload(name) for name in files])

        assert statuses(responses) == [200, 200, 201]
        [kept] = drafts_on_disk(media_root)
        manuscript.refresh_from_db()
        assert manuscript.draft_file_path == kept.relative_to(media_root / "private").as_posix()
        # El nombre, el tamaño y los bytes de la fila describen el mismo archivo.
        assert kept.read_bytes() == files[manuscript.draft_filename]
        assert manuscript.draft_size_bytes == kept.stat().st_size
        assert list((media_root / "tmp" / "uploads").glob("*")) == []
        assert AuditLog.objects.filter(action="MANUSCRIPT_DRAFT_FILE_UPLOADED").count() == 1
        assert AuditLog.objects.filter(action="MANUSCRIPT_DRAFT_FILE_REPLACED").count() == 2


class TestWithdrawalRacesTheWritePipelines:
    ROUNDS = 6

    def test_withdrawal_versus_submission_never_leaves_a_partial_version(self, owner, media_root) -> None:
        outcomes = set()
        for _ in range(self.ROUNDS):
            manuscript = ready_draft(owner, pdf=factory.clean_pdf(pages=1))

            responses = parallel(owner, [
                lambda client: client.post(
                    submit_url(manuscript), format="json", HTTP_IDEMPOTENCY_KEY="carrera-envio"
                ),
                lambda client: client.post(withdraw_url(manuscript), {}, format="json"),
            ])
            submitted, withdrawn = responses

            manuscript.refresh_from_db()
            assert withdrawn.status_code == 200 and manuscript.is_active is False
            versions = ManuscriptVersion.objects.filter(manuscript=manuscript).count()
            directory = version_dir_of(media_root, manuscript)
            if submitted.status_code == 201:
                # El envío ganó el bloqueo: existe completo y la baja lo respeta.
                assert versions == 1 and directory.is_dir() and manuscript.current_version == 1
                assert manuscript.status == "SUBMITTED"
                assert sha256_of_file(directory / "original.pdf") == ManuscriptVersion.objects.get(
                    manuscript=manuscript).original_sha256
            else:
                # La baja ganó: el envío se rechaza y no deja nada.
                assert submitted.status_code == 409
                assert versions == 0 and not directory.exists() and manuscript.status == "DRAFT"
                assert not CorrectionRound.objects.filter(manuscript=manuscript).exists()
            outcomes.add(submitted.status_code)
        assert outcomes <= {201, 409}
        assert_audit_chain_intact()

    def test_draft_upload_versus_submission_leaves_no_orphan_file(self, owner, media_root) -> None:
        original_pdf = factory.clean_pdf(pages=1)
        replacement = factory.clean_pdf(pages=3)
        for _ in range(self.ROUNDS):
            manuscript = ready_draft(owner, pdf=original_pdf)

            responses = parallel(owner, [
                lambda client: client.post(
                    submit_url(manuscript), format="json", HTTP_IDEMPOTENCY_KEY="carrera-carga"
                ),
                lambda client: client.post(
                    draft_url(manuscript), {"file": pdf_file(replacement)}, format="multipart"
                ),
            ])
            submitted, uploaded = responses

            assert submitted.status_code == 201 and uploaded.status_code in (200, 409)
            version = ManuscriptVersion.objects.get(manuscript=manuscript)
            expected = original_pdf if uploaded.status_code == 409 else replacement
            # La versión congela exactamente el borrador vigente al tomar el bloqueo.
            assert (version_dir_of(media_root, manuscript) / "original.pdf").read_bytes() == expected
            assert version.original_sha256 == hashlib.sha256(expected).hexdigest()
            manuscript.refresh_from_db()
            assert manuscript.status == "SUBMITTED" and manuscript.draft_file_path is None
        # El borrador consumido se borra tras el commit y el perdedor no deja archivo.
        assert drafts_on_disk(media_root) == []
        assert list((media_root / "tmp" / "uploads").glob("*")) == []
