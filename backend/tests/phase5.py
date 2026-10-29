"""Shared scenario of the Phase 5 end-to-end tests (TSK-79).

``Lifecycle`` drives a manuscript through the real endpoints, from the
author's submission to the verdict, with named people so the tests can look
for them in every artifact (notifications, audit, public pages, mail):
the author submits, the editor starts the review and assigns, the reviewer
writes and submits the evaluation, and the editor decides. Everything that
commits runs its ``on_commit`` callbacks, as in production.
"""

from __future__ import annotations

from dataclasses import dataclass

from rest_framework.test import APIClient

from apps.publications.models import Manuscript
from tests.publications import pdf_factory as factory
from tests.publications.test_manuscript_api import actor, client_for
from tests.publications.test_new_version import versions_url
from tests.publications.test_draft_file import pdf_file
from tests.publications.test_submission import ready_draft
from tests.reviews.test_editor_api import make_reviewer

AREA = "Agronomía"
TITLE = "Glaciares tropicales del Chimborazo"

AUTHOR_PERSON = {
    "first_name": "Marcela",
    "last_name": "Quizhpe Ordóñez",
    "email": "marcela.autora@unl.edu.ec",
}
AUTHOR_TOKENS = ("Marcela", "Quizhpe", "Ordóñez", "marcela.autora")
REVIEWER_PERSON = {
    "first_name": "Rodrigo",
    "last_name": "Valarezo Cueva",
    "email": "rodrigo.revisor@unl.edu.ec",
}
REVIEWER_TOKENS = ("Rodrigo", "Valarezo", "Cueva", "rodrigo.revisor")
EVALUATION = {
    "originality_score": 4,
    "methodology_score": 3,
    "clarity_score": 5,
    "relevance_score": 4,
    "ethics_score": 5,
    "recommendation": "ACCEPT",
    "comments_for_author": "Buen trabajo, con matices menores.",
    "confidential_comments": "COMENTARIO_CONFIDENCIAL_DEL_REVISOR",
}


@dataclass
class Lifecycle:
    """The people and the helpers of one editorial cycle."""

    author: object
    editor: object
    reviewer: object
    admin: object
    commits: object
    submit: object
    manuscript: Manuscript | None = None
    assignment: object = None

    @classmethod
    def create(cls, commits, submit) -> "Lifecycle":
        return cls(
            author=actor("AUTHOR", **AUTHOR_PERSON),
            editor=actor("EDITOR"),
            reviewer=make_reviewer(**REVIEWER_PERSON),
            admin=actor("ADMIN"),
            commits=commits,
            submit=submit,
        )

    def post(self, user, url, body=None, **extra):
        with self.commits(execute=True):
            return client_for(user).post(url, body or {}, format="json", **extra)

    def submit_manuscript(self) -> Manuscript:
        self.manuscript = ready_draft(
            self.author, pdf=factory.clean_pdf(pages=1), area=AREA, title=TITLE
        )
        assert self.submit(self.author, self.manuscript).status_code == 201
        self.manuscript.refresh_from_db()
        return self.manuscript

    def start_review(self):
        response = self.post(
            self.editor,
            f"/api/editor/submissions/{self.manuscript.pk}/start-review/",
            {"reviewer_id": str(self.reviewer.pk)},
        )
        assert response.status_code == 200, response.content
        from apps.reviews.models import Assignment

        self.assignment = Assignment.objects.get(manuscript=self.manuscript, status="ACTIVE")
        return self.assignment

    def evaluate(self):
        base = f"/api/reviewer/assignments/{self.assignment.pk}/evaluation/"
        client = client_for(self.reviewer)
        saved = client.put(base, EVALUATION, format="json", HTTP_IF_MATCH='"0"')
        assert saved.status_code == 200, saved.content
        with self.commits(execute=True):
            sent = client.post(f"{base}submit/", HTTP_IF_MATCH=saved["ETag"])
        assert sent.status_code == 200, sent.content

    def judge(self, body, key):
        self.manuscript.refresh_from_db()
        return self.post(
            self.editor,
            f"/api/editor/manuscripts/{self.manuscript.pk}/verdicts/",
            body,
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_IF_MATCH=f'"{self.manuscript.lock_version}"',
        )

    def accepted(self) -> Manuscript:
        """Submit, review, evaluate and accept."""
        self.submit_manuscript()
        self.start_review()
        self.evaluate()
        assert self.judge({"decision": "ACCEPTED"}, "acepta-1").status_code == 201
        self.manuscript.refresh_from_db()
        return self.manuscript

    def withdraw(self, user=None):
        return self.post(
            user or self.author,
            f"/api/manuscripts/{self.manuscript.pk}/withdraw/",
            {"reason": "Retiro por decisión de los autores."},
        )

    def authorize_correction(self, verdict_id, key="autoriza-1"):
        return self.post(
            self.admin,
            f"/api/admin/verdicts/{verdict_id}/authorize-correction/",
            {"reason": "El veredicto se registró sobre la evaluación equivocada."},
            HTTP_IDEMPOTENCY_KEY=key,
        )


def anonymous() -> APIClient:
    return APIClient()
