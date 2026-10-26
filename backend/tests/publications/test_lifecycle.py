"""End-to-end lifecycle, integrity from disk and permission matrix (TSK-40).

Covers the acceptance criteria of the testing task across the whole
manuscript module:

* the 50 MB / 50 MB + 1 byte limits and the rejection of active content
  are exercised on every upload endpoint;
* a previous version is never overwritten and a withdrawal deletes
  nothing — checked by recomputing every hash from the files on disk,
  the way ``verify_integrity`` will (TSK-76);
* a failed audit or storage never leaves a partial version (see
  ``test_failure_injection.py``).

The permission matrix runs every manuscript endpoint against every kind
of actor, so a new endpoint cannot ship without an explicit answer.
"""

from __future__ import annotations

import hashlib
import json

import pikepdf
import pytest

from apps.audit.models import AuditLog
from apps.audit.services import canonical_event_json, compute_entry_hash
from apps.publications.models import (
    CorrectionRound,
    Manuscript,
    ManuscriptAuthor,
    ManuscriptVersion,
    StatusEvent,
)
from apps.publications.services.pdf import find_active_content, sha256_of_file
from apps.publications.services.snapshot import canonical_json, metadata_sha256
from tests.factories import ManuscriptAuthorFactory
from tests.publications import pdf_factory as factory
from tests.publications.test_draft_file import draft_url, pdf_file
from tests.publications.test_manuscript_api import (  # noqa: F401
    URL,
    actor,
    client_for,
    detail_url,
    owned_manuscript,
)
from tests.publications.test_new_version import (  # noqa: F401
    request_corrections,
    send,
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
from tests.publications.test_versions_history import file_url, history_url, versions_url
from tests.publications.test_withdraw import withdraw, withdraw_url  # noqa: F401

pytestmark = pytest.mark.django_db

V1 = factory.pdf_with_identity()
V2 = factory.clean_pdf(pages=2)
V3 = factory.clean_pdf(pages=3)


def assert_audit_chain_intact() -> None:
    """Every entry links to the previous one and its hash is reproducible."""
    previous = None
    for entry in AuditLog.objects.order_by("id"):
        assert entry.previous_hash == previous
        event = {
            "occurred_at": entry.occurred_at,
            "actor_id": str(entry.actor_id) if entry.actor_id else None,
            "actor_role": entry.actor_role,
            "action": entry.action,
            "entity_type": entry.entity_type,
            "entity_id": str(entry.entity_id) if entry.entity_id else None,
            "result": entry.result,
            "reason": entry.reason,
            "request_id": entry.request_id,
            "ip_address": entry.ip_address,
            "user_agent": entry.user_agent,
            "details": entry.details,
        }
        assert compute_entry_hash(canonical_event_json(event), previous) == entry.entry_hash
        previous = entry.entry_hash


def assert_version_matches_its_files(media_root, version: ManuscriptVersion) -> None:
    """Recompute every seal from disk, as the integrity check does."""
    private = media_root / "private"
    original = private / version.original_file_path
    sanitized = private / version.sanitized_file_path
    metadata_file = original.parent / "metadata.json"

    assert sha256_of_file(original) == version.original_sha256
    assert original.stat().st_size == version.original_size_bytes
    assert sha256_of_file(sanitized) == version.sanitized_sha256
    assert metadata_file.read_bytes() == canonical_json(version.metadata_snapshot).encode("utf-8")
    assert metadata_sha256(canonical_json(version.metadata_snapshot)) == version.metadata_sha256
    assert hashlib.sha256(metadata_file.read_bytes()).hexdigest() == version.metadata_sha256
    assert json.loads(metadata_file.read_text(encoding="utf-8")) == version.metadata_snapshot

    with pikepdf.open(sanitized) as pdf:
        assert "/Info" not in pdf.trailer and "/Metadata" not in pdf.Root
        assert all("/Annots" not in page and "/PieceInfo" not in page for page in pdf.pages)
        assert find_active_content(pdf) == []


def tree_digest(directory) -> dict:
    return {path.name: sha256_of_file(path) for path in sorted(directory.iterdir())}


class TestFullLifecycle:
    def test_three_iterations_stay_intact_and_a_withdrawal_deletes_nothing(
        self, owner, submit, send, withdraw, media_root
    ) -> None:
        manuscript = ready_draft(owner, pdf=V1, name="Ana Lopez - v1.pdf")
        assert submit(owner, manuscript).status_code == 201
        v1_digest = tree_digest(version_dir_of(media_root, manuscript, 1))

        request_corrections(manuscript, round_number=1)
        manuscript.refresh_from_db()
        edited = client_for(owner).patch(
            detail_url(manuscript),
            {"abstract": "Resumen ampliado tras la primera revisión."},
            format="json",
            HTTP_IF_MATCH=f'"{manuscript.lock_version}"',
        )
        assert edited.status_code == 200
        assert send(owner, manuscript, pdf_file(V2, name="v2.pdf"), key="v2").status_code == 201
        v2_digest = tree_digest(version_dir_of(media_root, manuscript, 2))
        assert tree_digest(version_dir_of(media_root, manuscript, 1)) == v1_digest

        request_corrections(manuscript, round_number=2)
        assert send(owner, manuscript, pdf_file(V3, name="v3.pdf"), key="v3").status_code == 201

        versions = list(ManuscriptVersion.objects.filter(manuscript=manuscript).order_by("version_number"))
        assert [(v.version_number, v.round_number) for v in versions] == [(1, 0), (2, 1), (3, 2)]
        for version in versions:
            assert_version_matches_its_files(media_root, version)
        assert tree_digest(version_dir_of(media_root, manuscript, 1)) == v1_digest
        assert tree_digest(version_dir_of(media_root, manuscript, 2)) == v2_digest

        # Cada iteración conserva su propio PDF y su propia instantánea.
        assert len({v.original_sha256 for v in versions}) == 3
        assert versions[0].metadata_snapshot["abstract"] == "Resumen del estudio de campo."
        assert versions[1].metadata_snapshot["abstract"] == "Resumen ampliado tras la primera revisión."
        assert versions[2].metadata_snapshot == versions[1].metadata_snapshot

        rounds = {r.round_number: r for r in CorrectionRound.objects.filter(manuscript=manuscript)}
        assert {n: r.closed_by_version.version_number for n, r in rounds.items()} == {0: 1, 1: 2, 2: 3}

        before = {
            "versions": [(v.pk, v.original_sha256, v.metadata_sha256) for v in versions],
            "rounds": CorrectionRound.objects.filter(manuscript=manuscript).count(),
            "authors": ManuscriptAuthor.objects.filter(manuscript=manuscript).count(),
            "events": StatusEvent.objects.filter(manuscript=manuscript).count(),
            "files": {n: tree_digest(version_dir_of(media_root, manuscript, n)) for n in (1, 2, 3)},
        }

        assert withdraw(owner, manuscript, {"reason": "Cierro el proceso."}).status_code == 200

        manuscript.refresh_from_db()
        assert manuscript.is_active is False and manuscript.status == "SUBMITTED"
        assert [(v.pk, v.original_sha256, v.metadata_sha256) for v in
                ManuscriptVersion.objects.filter(manuscript=manuscript).order_by("version_number")] == before["versions"]
        assert CorrectionRound.objects.filter(manuscript=manuscript).count() == before["rounds"]
        assert ManuscriptAuthor.objects.filter(manuscript=manuscript).count() == before["authors"]
        assert StatusEvent.objects.filter(manuscript=manuscript).count() == before["events"] + 1
        assert {n: tree_digest(version_dir_of(media_root, manuscript, n)) for n in (1, 2, 3)} == before["files"]
        for version in ManuscriptVersion.objects.filter(manuscript=manuscript):
            assert_version_matches_its_files(media_root, version)
        assert_audit_chain_intact()

    def test_the_editor_reads_the_same_history_after_the_withdrawal(self, owner, submit, send, withdraw) -> None:
        manuscript = ready_draft(owner, pdf=V1)
        submit(owner, manuscript)
        request_corrections(manuscript)
        send(owner, manuscript, pdf_file(V2), key="v2")
        withdraw(owner, manuscript, {"reason": "Cierro el proceso."})

        mine = client_for(owner).get(history_url(manuscript)).json()
        theirs = client_for(actor("EDITOR")).get(history_url(manuscript)).json()

        assert theirs == mine
        assert [e["type"] for e in mine["results"]][-1] == "WITHDRAWN"
        assert sum(1 for e in mine["results"] if e["type"] == "VERSION_SUBMITTED") == 2

    def test_every_version_can_still_be_downloaded_exactly_after_the_withdrawal(
        self, owner, submit, send, withdraw, media_root
    ) -> None:
        manuscript = ready_draft(owner, pdf=V1)
        submit(owner, manuscript)
        request_corrections(manuscript)
        send(owner, manuscript, pdf_file(V2), key="v2")
        withdraw(owner, manuscript, {"reason": "Cierro el proceso."})

        for version, expected in zip(ManuscriptVersion.objects.filter(manuscript=manuscript).order_by("version_number"), (V1, V2)):
            response = client_for(owner).get(file_url(manuscript, version))
            assert response.status_code == 200
            served = media_root / "private" / response["X-Accel-Redirect"].removeprefix("/_protected/")
            assert served.read_bytes() == expected

    def test_a_failed_attempt_in_the_middle_leaves_the_audit_chain_intact(
        self, owner, submit, send, media_root
    ) -> None:
        manuscript = ready_draft(owner, pdf=V1)
        submit(owner, manuscript)
        request_corrections(manuscript)
        assert send(owner, manuscript, pdf_file(V1), key="sin-cambios").status_code == 400
        assert send(owner, manuscript, pdf_file(b"corrupto"), key="corrupto").status_code == 400
        assert send(owner, manuscript, pdf_file(V2), key="bueno").status_code == 201

        assert_audit_chain_intact()
        assert ManuscriptVersion.objects.filter(manuscript=manuscript).count() == 2


UPLOAD_ENDPOINTS = ("draft-file", "versions")


class TestPdfRulesOnEveryUploadEndpoint:
    """The same PDF rules hold wherever a file can enter the system."""

    @pytest.fixture
    def target(self, owner, submit):
        def prepare(endpoint):
            if endpoint == "draft-file":
                manuscript = owned_manuscript(owner)
                return manuscript, lambda data: client_for(owner).post(
                    draft_url(manuscript), {"file": pdf_file(data)}, format="multipart"
                )
            manuscript = ready_draft(owner, pdf=V1)
            submit(owner, manuscript)
            request_corrections(manuscript)
            counter = iter(range(1000))
            return manuscript, lambda data: client_for(owner).post(
                versions_url(manuscript),
                {"file": pdf_file(data)},
                format="multipart",
                HTTP_IDEMPOTENCY_KEY=f"carga-{next(counter)}",
            )

        return prepare

    @pytest.mark.parametrize("endpoint", UPLOAD_ENDPOINTS)
    def test_exactly_50_mb_is_accepted_and_one_byte_more_is_413(self, target, endpoint) -> None:
        _, upload = target(endpoint)
        exact = factory.pdf_of_size(50 * factory.MIB)

        assert upload(exact + b"\n").status_code == 413
        assert upload(exact).status_code == 201

    @pytest.mark.parametrize("endpoint", UPLOAD_ENDPOINTS)
    @pytest.mark.parametrize(
        "kind", ["/JavaScript", "/OpenAction", "/AA", "/Launch", "/EmbeddedFiles", "inline-javascript"]
    )
    def test_active_content_is_rejected(self, target, endpoint, kind) -> None:
        _, upload = target(endpoint)

        response = upload(factory.pdf_with_active_content(kind))

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "PDF_INVALID"
        assert response.json()["error"]["details"]["active_content"]

    @pytest.mark.parametrize("endpoint", UPLOAD_ENDPOINTS)
    @pytest.mark.parametrize(
        "data",
        [
            pytest.param(b"", id="vacio"),
            pytest.param(b"texto plano con extension pdf", id="extension-enganosa"),
            pytest.param(V2[:120], id="truncado"),
            pytest.param(factory.encrypted_pdf("clave"), id="cifrado"),
            pytest.param(factory.pdf_without_pages(), id="sin-paginas"),
        ],
    )
    def test_a_file_that_is_not_a_readable_pdf_is_rejected(self, target, endpoint, data) -> None:
        _, upload = target(endpoint)

        response = upload(data)

        assert response.status_code == 400 and response.json()["error"]["code"] == "PDF_INVALID"

    @pytest.mark.parametrize("endpoint", UPLOAD_ENDPOINTS)
    def test_a_rejected_upload_leaves_no_trace_in_the_volume(self, target, endpoint, media_root) -> None:
        manuscript, upload = target(endpoint)
        before = sorted(p.relative_to(media_root).as_posix() for p in media_root.rglob("*") if p.is_file())

        upload(factory.pdf_with_active_content("/JavaScript"))
        upload(b"basura")

        after = sorted(p.relative_to(media_root).as_posix() for p in media_root.rglob("*") if p.is_file())
        assert after == before


@pytest.fixture
def scene(owner, submit, send):
    """A submitted manuscript with two versions, plus every kind of actor."""
    manuscript = ready_draft(owner, pdf=V1)
    submit(owner, manuscript)
    request_corrections(manuscript)
    send(owner, manuscript, pdf_file(V2), key="v2")
    manuscript.refresh_from_db()

    conflicted = actor("EDITOR")
    ManuscriptAuthorFactory(
        manuscript=manuscript, user=conflicted, email=conflicted.email,
        full_name=conflicted.get_full_name(), author_order=9,
    )
    return {
        "manuscript": manuscript,
        "version": ManuscriptVersion.objects.get(manuscript=manuscript, version_number=1),
        "actors": {
            "admin": actor("ADMIN"),
            "reviewer": actor("REVIEWER"),
            "no-roles": actor(),
            "foreign-author": actor("AUTHOR"),
            "editor": actor("EDITOR"),
            "conflicted-editor": conflicted,
        },
    }


ENDPOINTS = {
    "detail": ("get", lambda m, v: detail_url(m)),
    "patch": ("patch", lambda m, v: detail_url(m)),
    "draft-file": ("post", lambda m, v: draft_url(m)),
    "submit": ("post", lambda m, v: submit_url(m)),
    "versions-list": ("get", lambda m, v: versions_url(m)),
    "versions-post": ("post", lambda m, v: versions_url(m)),
    "version-file": ("get", lambda m, v: file_url(m, v)),
    "history": ("get", lambda m, v: history_url(m)),
    "withdraw": ("post", lambda m, v: withdraw_url(m)),
}
READS = {"detail", "versions-list", "version-file", "history"}

#: Expected answer per actor: a fixed code, or a (read, write) pair.
EXPECTED = {
    "anonymous": 401,
    "admin": 403,
    "reviewer": 403,
    "no-roles": 403,
    "foreign-author": 404,
    "editor": (200, 403),
    "conflicted-editor": (404, 403),
}


def call(client, method: str, url: str):
    """GETs carry no body; every other method sends an empty JSON object."""
    if method == "get":
        return client.get(url)
    return getattr(client, method)(url, {}, format="json")


def state_of(manuscript) -> tuple:
    """What a denied request must leave exactly as it was."""
    return (
        Manuscript.objects.values_list(
            "status", "is_active", "lock_version", "current_version"
        ).get(pk=manuscript.pk),
        ManuscriptVersion.objects.count(),
        AuditLog.objects.filter(
            action__in=["MANUSCRIPT_FILE_DOWNLOADED", "MANUSCRIPT_WITHDRAWN"]
        ).count(),
    )


class TestPermissionMatrix:
    @pytest.mark.parametrize("who", sorted(EXPECTED))
    def test_every_endpoint_answers_this_actor_as_the_plan_says(self, scene, who) -> None:
        from rest_framework.test import APIClient

        client = APIClient() if who == "anonymous" else client_for(scene["actors"][who])
        manuscript = scene["manuscript"]
        mismatches = []

        for endpoint, (method, build_url) in sorted(ENDPOINTS.items()):
            expected = EXPECTED[who]
            if isinstance(expected, tuple):
                expected = expected[0] if endpoint in READS else expected[1]
            before = state_of(manuscript)

            response = call(client, method, build_url(manuscript, scene["version"]))

            if response.status_code != expected:
                mismatches.append((endpoint, expected, response.status_code))
            if expected != 200:
                # Una solicitud denegada no cambia nada ni entrega el archivo.
                assert "X-Accel-Redirect" not in response.headers, endpoint
                assert state_of(manuscript) == before, endpoint

        assert mismatches == [], f"{who}: (endpoint, esperado, obtenido)"

    def test_the_admin_never_reaches_a_manuscript_by_any_endpoint(self, scene) -> None:
        admin = client_for(scene["actors"]["admin"])
        manuscript, version = scene["manuscript"], scene["version"]

        for name, (method, build_url) in ENDPOINTS.items():
            assert call(admin, method, build_url(manuscript, version)).status_code == 403, name
        assert admin.get(URL).status_code == 403
        assert admin.post(URL, {}, format="json").status_code == 403

    def test_the_list_never_leaks_a_manuscript_to_an_actor_outside_its_scope(self, scene) -> None:
        ids = {str(scene["manuscript"].pk)}

        for who in ("foreign-author", "conflicted-editor"):
            body = client_for(scene["actors"][who]).get(URL).json()
            assert not ids & {item["id"] for item in body["results"]}, who
        editor_ids = {i["id"] for i in client_for(scene["actors"]["editor"]).get(URL).json()["results"]}
        assert ids <= editor_ids
