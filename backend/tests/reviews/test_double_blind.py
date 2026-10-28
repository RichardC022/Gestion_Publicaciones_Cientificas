"""Double-blind acceptance tests over the whole review cycle (TSK-65).

One realistic cycle runs through the real API with real PDFs: the author
submits a file full of identity, the editor starts the review, the
reviewer reads, reports a leak and evaluates, the editor judges and
dismisses the report, and the author reads the outcome. Every response
each side received is kept, so the plan's mandatory no-leak checks
(section 2.9) look at the serialized text and a value under any key
fails too:

1. the reviewer's payloads hold no authorship, contact, snapshot, file
   name, path or hash;
2. the PDF the reviewer is sent holds no ``/Info``, XMP, ``/EmbeddedFiles``,
   ``/JavaScript``, ``/OpenAction``, ``/AA`` nor ``/Launch`` anywhere in
   its object graph (and the checker itself is proven on dirty files);
3. the events the notifications will build from carry identifiers only;
4. the author reads neither the reviewer's identity, the confidential
   comments nor the scores;
5. an assignment that is not the reviewer's answers ``404``, never ``403``,
   and no differently from one that does not exist.
"""

from __future__ import annotations

import re
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import pikepdf
import pytest
from rest_framework.test import APIClient

from apps.publications import signals as publications_signals
from apps.publications.models import ManuscriptVersion
from apps.reviews.models import IncidentReport
from apps.reviews import signals as reviews_signals
from tests.factories import AssignmentFactory, FinalEvaluationFactory
from tests.publications import pdf_factory as factory
from tests.publications.test_manuscript_api import (  # noqa: F401
    actor,
    author_payload,
    client_for,
    coauthor,
    detail_url as manuscript_url,
    error_code,
)
from tests.publications.test_submission import (  # noqa: F401
    media_root,
    ready_draft,
    seeded_roles,
    submit,
)
from tests.reviews.test_editor_api import make_reviewer

pytestmark = pytest.mark.django_db

REVIEWER_BASE = "/api/reviewer/"
EDITOR_BASE = "/api/editor/"

OWNER_NAME = ("Beatriz", "Autorreservada")
COAUTHOR_NAME = "Carlos Coautor Reservado"
COAUTHOR_EMAIL = "carlos.reservado@otra.edu"
COAUTHOR_AFFILIATION = "Instituto Secreto de Estudios"
ORIGINAL_FILENAME = "beatriz-autorreservada-articulo-final.pdf"
REVIEWER_NAME = ("Rafael", "Revisor Reservado")
CONFIDENTIAL = "nota-confidencial-solo-para-el-editor"
LEAK_TEXT = "El PDF menciona al grupo de investigación de los autores."
OBSERVATIONS = "Corrija la sección de métodos."

#: Strings that the identity-laden fixture PDF carries in the original.
PDF_IDENTITY_MARKERS = (b"Ana L", b"Word de Ana", b"Comentario de Ana")

FORBIDDEN_KEYS = (
    "/Info",
    "/Metadata",
    "/EmbeddedFiles",
    "/EmbeddedFile",
    "/JavaScript",
    "/JS",
    "/OpenAction",
    "/AA",
    "/Launch",
)


def forbidden_features(path: Path) -> set[str]:
    """Every forbidden feature found anywhere in the object graph of the PDF.

    It walks from the trailer through direct and indirect objects alike:
    ``pdf.objects`` alone misses what lives in a direct dictionary, such
    as an action inside an annotation or the ``/Names`` of the catalog.
    """
    found: set[str] = set()
    seen: set[tuple[int, int]] = set()

    def scan(obj) -> None:
        if not isinstance(obj, pikepdf.Object):
            return
        if obj.is_indirect:
            if obj.objgen in seen:
                return
            seen.add(obj.objgen)
        if obj._type_code == pikepdf.ObjectType.array:
            for item in obj:
                scan(item)
        elif obj._type_code in (pikepdf.ObjectType.dictionary, pikepdf.ObjectType.stream):
            for key, value in obj.items():
                if key in FORBIDDEN_KEYS:
                    found.add(key)
                scan(value)
            if obj.get("/S") in (pikepdf.Name.JavaScript, pikepdf.Name.Launch):
                found.add(str(obj.get("/S")))
            if obj.get("/Type") == pikepdf.Name.Metadata:
                found.add("/Metadata")

    with pikepdf.open(path) as pdf:
        scan(pdf.trailer)
    return found


def served_path(media_root: Path, response) -> Path:
    """The file Nginx would send for an ``X-Accel-Redirect`` answer."""
    internal = response["X-Accel-Redirect"]
    assert internal.startswith("/_protected/")
    return media_root / "private" / internal.removeprefix("/_protected/")


SIGNALS = {
    "assignment_created": reviews_signals.assignment_created,
    "assignment_revoked": reviews_signals.assignment_revoked,
    "assignment_expired": reviews_signals.assignment_expired,
    "evaluation_submitted": reviews_signals.evaluation_submitted,
    "reviewer_conflict_declared": reviews_signals.reviewer_conflict_declared,
    "incident_reported": reviews_signals.incident_reported,
    "incident_resolved": reviews_signals.incident_resolved,
    "manuscript_submitted": publications_signals.manuscript_submitted,
    "new_version_submitted": publications_signals.new_version_submitted,
    "manuscript_withdrawn": publications_signals.manuscript_withdrawn,
    "verdict_registered": publications_signals.verdict_registered,
}


@dataclass
class Cycle:
    """What each side of the review cycle received, and the events it raised."""

    owner: object
    reviewer: object
    editor: object
    manuscript: object
    assignment: object
    incident: object
    document: object
    reviewer_texts: list[str] = field(default_factory=list)
    author_texts: list[str] = field(default_factory=list)
    events: list[tuple[str, dict]] = field(default_factory=list)


@pytest.fixture
def cycle(media_root, submit, django_capture_on_commit_callbacks) -> Cycle:
    owner = actor("AUTHOR", first_name=OWNER_NAME[0], last_name=OWNER_NAME[1])
    reviewer = make_reviewer(first_name=REVIEWER_NAME[0], last_name=REVIEWER_NAME[1])
    editor = actor("EDITOR", first_name="Elena", last_name="Editora")
    events: list[tuple[str, dict]] = []

    def listen(name):
        def listener(sender, **kwargs):
            kwargs.pop("signal", None)
            events.append((name, kwargs))

        return listener

    def step(call):
        with django_capture_on_commit_callbacks(execute=True):
            return call()

    reviewer_texts: list[str] = []
    author_texts: list[str] = []

    def reviewer_gets(response, *statuses: int):
        assert response.status_code in statuses, response.content
        # Nginx consume `X-Accel-Redirect` y no lo reenvía: el cliente no lo recibe.
        received = {k: v for k, v in response.headers.items() if k.lower() != "x-accel-redirect"}
        reviewer_texts.append(response.content.decode() + str(received))
        return response

    with ExitStack() as stack:
        for name, signal in SIGNALS.items():
            listener = listen(name)
            signal.connect(listener, weak=False)
            stack.callback(signal.disconnect, listener)

        manuscript = ready_draft(
            owner,
            pdf=factory.pdf_with_identity(),
            name=ORIGINAL_FILENAME,
            authors=author_payload(
                owner,
                coauthor(
                    COAUTHOR_EMAIL, full_name=COAUTHOR_NAME, affiliation=COAUTHOR_AFFILIATION
                ),
            ),
        )
        assert submit(owner, manuscript).status_code == 201
        started = step(
            lambda: client_for(editor).post(
                f"{EDITOR_BASE}submissions/{manuscript.pk}/start-review/",
                {"reviewer_id": str(reviewer.pk)},
                format="json",
            )
        )
        assert started.status_code == 200, started.content
        manuscript.refresh_from_db()
        assignment = manuscript.assignments.get()
        client = client_for(reviewer)
        base = f"{REVIEWER_BASE}assignments/{assignment.pk}/"

        reviewer_gets(client.get(f"{REVIEWER_BASE}assignments/"), 200)
        reviewer_gets(client.get(base), 200)
        document = reviewer_gets(client.get(f"{base}document/"), 200)
        reviewer_gets(client.get(f"{base}evaluation/"), 200)
        leak = reviewer_gets(
            step(
                lambda: client.post(
                    f"{base}identity-leak/",
                    {"report_type": "IDENTITY_LEAK", "description": LEAK_TEXT},
                    format="json",
                )
            ),
            201,
        )
        saved = reviewer_gets(
            client.put(
                f"{base}evaluation/",
                {
                    "originality_score": 4,
                    "methodology_score": 3,
                    "clarity_score": 5,
                    "relevance_score": 4,
                    "ethics_score": 5,
                    "recommendation": "REQUIRES_CORRECTIONS",
                    "comments_for_author": "Aclare la metodología.",
                    "confidential_comments": CONFIDENTIAL,
                },
                format="json",
                HTTP_IF_MATCH='"0"',
            ),
            200,
        )
        reviewer_gets(
            step(
                lambda: client.post(
                    f"{base}evaluation/submit/", HTTP_IF_MATCH=saved["ETag"]
                )
            ),
            200,
        )
        # Rutas que deben negarse sin revelar nada.
        reviewer_gets(client.put(f"{base}evaluation/", {}, format="json", HTTP_IF_MATCH='"2"'), 409)
        reviewer_gets(client.post(f"{base}conflict/", {}, format="json"), 409)
        final = client.get(f"{base}evaluation/").json()
        history = reviewer_gets(client.get(f"{REVIEWER_BASE}evaluations/"), 200)
        reviewer_gets(client.get(f"{REVIEWER_BASE}evaluations/{final['id']}/"), 200)

        manuscript.refresh_from_db()
        verdict = step(
            lambda: client_for(editor).post(
                f"{EDITOR_BASE}manuscripts/{manuscript.pk}/verdicts/",
                {"decision": "REQUIRES_CORRECTIONS", "observations": OBSERVATIONS},
                format="json",
                HTTP_IDEMPOTENCY_KEY="clave-ciego",
                HTTP_IF_MATCH=f'"{manuscript.lock_version}"',
            )
        )
        assert verdict.status_code == 201, verdict.content
        incident = IncidentReport.objects.get(pk=leak.json()["id"])
        resolved = step(
            lambda: client_for(editor).post(
                f"{EDITOR_BASE}incidents/{incident.pk}/resolve/",
                {"resolution": "DISMISS"},
                format="json",
            )
        )
        assert resolved.status_code == 200, resolved.content
        reviewer_gets(client.get(f"{REVIEWER_BASE}evaluations/"), 200)
        assert history.status_code == 200

        author_client = client_for(owner)
        for url in (
            manuscript_url(manuscript),
            f"{manuscript_url(manuscript)}history/",
            f"{manuscript_url(manuscript)}versions/",
            "/api/manuscripts/",
        ):
            response = author_client.get(url)
            assert response.status_code == 200, url
            author_texts.append(response.content.decode() + str(response.headers))

    return Cycle(
        owner=owner,
        reviewer=reviewer,
        editor=editor,
        manuscript=manuscript,
        assignment=assignment,
        incident=incident,
        document=document,
        reviewer_texts=reviewer_texts,
        author_texts=author_texts,
        events=events,
    )


def version_of(cycle: Cycle) -> ManuscriptVersion:
    return ManuscriptVersion.objects.get(manuscript=cycle.manuscript, version_number=1)


class TestReviewerNeverSeesAuthorship:
    """Mandatory no-leak check 1, over every response the reviewer received."""

    def test_no_identifying_value_in_any_response(self, cycle) -> None:
        version = version_of(cycle)
        secrets = [
            *OWNER_NAME,
            cycle.owner.get_full_name(),
            cycle.owner.email,
            cycle.owner.institutional_id,
            COAUTHOR_NAME,
            COAUTHOR_EMAIL,
            COAUTHOR_AFFILIATION,
            "Universidad Nacional de Loja",
            ORIGINAL_FILENAME,
            ORIGINAL_FILENAME.removesuffix(".pdf"),
            version.original_sha256,
            version.sanitized_sha256,
            version.metadata_sha256,
            "original.pdf",
            "sanitized.pdf",
            "original_file_path",
            "sanitized_file_path",
            "metadata_snapshot",
            "created_by",
            "submitted_by",
            "authors",
            "affiliation",
            '"email"',
            "Ana López",
        ]
        text = "\n".join(cycle.reviewer_texts).lower()

        assert len(cycle.reviewer_texts) >= 10
        for secret in secrets:
            assert secret.lower() not in text, secret

    def test_the_reviewers_own_content_does_reach_them(self, cycle) -> None:
        """Guards the check above against an empty or failed scenario."""
        text = "\n".join(cycle.reviewer_texts)

        assert cycle.manuscript.code in text
        assert "Efecto del clima en cultivos andinos" in text
        assert CONFIDENTIAL in text


class TestSanitizedPdf:
    """Mandatory no-leak check 2, with ``pikepdf`` over the whole object graph."""

    def test_the_file_sent_to_the_reviewer_is_clean(self, cycle, media_root) -> None:
        path = served_path(media_root, cycle.document)

        assert path.name == "sanitized.pdf"
        assert forbidden_features(path) == set()
        raw = path.read_bytes()
        for marker in PDF_IDENTITY_MARKERS:
            assert marker not in raw
        assert b"<?xpacket" not in raw and b"x:xmpmeta" not in raw

    def test_the_original_does_carry_the_identity(self, cycle, media_root) -> None:
        """So the clean result above is the sanitizer's doing, not the fixture's."""
        original = (
            media_root / "private" / "manuscripts" / str(cycle.manuscript.pk) / "v0001" / "original.pdf"
        )

        assert {"/Info", "/Metadata"} <= forbidden_features(original)
        assert any(marker in original.read_bytes() for marker in PDF_IDENTITY_MARKERS)
        assert version_of(cycle).original_sha256 != version_of(cycle).sanitized_sha256

    def test_the_document_url_never_points_to_the_original(self, cycle) -> None:
        assert cycle.document["X-Accel-Redirect"].endswith("/v0001/sanitized.pdf")
        assert "original" not in cycle.document["X-Accel-Redirect"]

    @pytest.mark.parametrize(
        "kind",
        ["/JavaScript", "/OpenAction", "/AA", "/Launch", "/EmbeddedFiles", "inline-javascript"],
    )
    def test_the_checker_catches_each_forbidden_feature(self, kind, tmp_path) -> None:
        dirty = tmp_path / "dirty.pdf"
        dirty.write_bytes(factory.pdf_with_active_content(kind))

        assert forbidden_features(dirty) != set()

    def test_the_checker_accepts_a_clean_file(self, tmp_path) -> None:
        clean = tmp_path / "clean.pdf"
        clean.write_bytes(factory.clean_pdf())

        assert forbidden_features(clean) == set()


IDENTIFIER_CODE = re.compile(r"^[A-Z][A-Z_]*$")
FORBIDDEN_PAYLOAD_KEYS = {
    "name", "full_name", "email", "reason", "description", "justification",
    "observations", "comments", "title", "affiliation", "filename",
}


class TestEventsCarryIdentifiersOnly:
    """Mandatory no-leak check 3: what the notifications will be built from."""

    def test_the_cycle_raised_the_expected_events(self, cycle) -> None:
        raised = {name for name, _ in cycle.events}

        assert {
            "manuscript_submitted",
            "assignment_created",
            "incident_reported",
            "evaluation_submitted",
            "verdict_registered",
            "incident_resolved",
        } <= raised

    def test_every_payload_value_is_an_identifier_or_a_code(self, cycle) -> None:
        for name, payload in cycle.events:
            assert not FORBIDDEN_PAYLOAD_KEYS & set(payload), name
            for key, value in payload.items():
                assert value is None or isinstance(value, (UUID, int)) or (
                    isinstance(value, str) and IDENTIFIER_CODE.match(value)
                ), (name, key, value)

    def test_no_payload_holds_a_name_a_contact_or_free_text(self, cycle) -> None:
        text = " ".join(str(payload) for _, payload in cycle.events).lower()

        for secret in (
            *OWNER_NAME,
            *REVIEWER_NAME,
            COAUTHOR_NAME,
            COAUTHOR_EMAIL,
            LEAK_TEXT,
            CONFIDENTIAL,
            OBSERVATIONS,
            cycle.owner.email,
            cycle.reviewer.email,
        ):
            assert secret.lower() not in text, secret


class TestAuthorNeverSeesTheReviewer:
    """Mandatory no-leak check 4, after the evaluation, the verdict and the report."""

    def test_no_reviewer_identity_nor_confidential_comments(self, cycle) -> None:
        secrets = [
            *REVIEWER_NAME,
            cycle.reviewer.get_full_name(),
            cycle.reviewer.email,
            cycle.reviewer.institutional_id,
            str(cycle.reviewer.pk),
            str(cycle.assignment.pk),
            str(cycle.incident.pk),
            CONFIDENTIAL,
            LEAK_TEXT,
            "confidential_comments",
            "reviewer",
            "originality_score",
            "ethics_score",
            "IDENTITY_LEAK",
        ]
        text = "\n".join(cycle.author_texts).lower()

        for secret in secrets:
            assert secret.lower() not in text, secret

    def test_the_author_does_read_what_is_theirs(self, cycle) -> None:
        """The allowed feedback arrives: comments for the author and the observations."""
        text = "\n".join(cycle.author_texts)

        assert "Aclare la metodología." in text
        assert OBSERVATIONS in text
        assert "REQUIRES_CORRECTIONS" in text


class TestForeignAssignmentsAnswer404:
    """Mandatory no-leak check 5: not the reviewer's means not found, never forbidden."""

    @pytest.fixture
    def foreign(self):
        owner_of_it = make_reviewer()
        assignment = AssignmentFactory(reviewer=owner_of_it)
        evaluation = FinalEvaluationFactory(assignment=assignment)
        return assignment, evaluation

    @staticmethod
    def calls(assignment, evaluation):
        base = f"{REVIEWER_BASE}assignments/{assignment.pk}/"
        body = {"report_type": "OTHER", "description": "Texto."}
        return [
            ("get", base, None, {}),
            ("get", f"{base}document/", None, {}),
            ("get", f"{base}evaluation/", None, {}),
            ("put", f"{base}evaluation/", {}, {"HTTP_IF_MATCH": '"0"'}),
            ("post", f"{base}evaluation/submit/", None, {"HTTP_IF_MATCH": '"0"'}),
            ("post", f"{base}conflict/", {}, {}),
            ("post", f"{base}identity-leak/", body, {}),
            ("get", f"{REVIEWER_BASE}evaluations/{evaluation.pk}/", None, {}),
        ]

    def test_every_endpoint_answers_404_with_the_same_envelope_as_a_missing_one(
        self, foreign
    ) -> None:
        assignment, evaluation = foreign
        stranger = make_reviewer()
        client = client_for(stranger)
        ghost = AssignmentFactory.build()  # an id that exists nowhere
        ghost_evaluation = FinalEvaluationFactory.build(assignment=ghost)

        for (method, url, body, extra), (_, ghost_url, _, _) in zip(
            self.calls(assignment, evaluation), self.calls(ghost, ghost_evaluation)
        ):
            kwargs = {"format": "json", **extra} if body is not None else dict(extra)
            args = (url, body) if body is not None else (url,)
            ghost_args = (ghost_url, body) if body is not None else (ghost_url,)
            real = getattr(client, method)(*args, **kwargs)
            missing = getattr(client, method)(*ghost_args, **kwargs)

            assert real.status_code == 404, url
            assert real.status_code == missing.status_code
            assert error_code(real) == error_code(missing) == "NOT_FOUND"
            assert real.json()["error"]["message"] == missing.json()["error"]["message"]

    def test_a_role_without_the_module_is_forbidden_not_hidden(self, foreign) -> None:
        assignment, _ = foreign

        response = client_for(actor("AUTHOR")).get(f"{REVIEWER_BASE}assignments/{assignment.pk}/")

        assert response.status_code == 403

    def test_anonymous_requests_are_unauthorized(self, foreign) -> None:
        assignment, _ = foreign

        response = APIClient().get(f"{REVIEWER_BASE}assignments/{assignment.pk}/")

        assert response.status_code == 401
