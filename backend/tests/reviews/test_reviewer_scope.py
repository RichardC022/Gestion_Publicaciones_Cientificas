"""Tests for the reviewer's scope, serializers and permission (TSK-60).

Covers the acceptance criteria: the reviewer's payload carries no
authorship, contact, snapshot, file name, path or hash; a foreign
assignment or a withdrawn manuscript answers ``404``; and a reviewer who
is an author or coauthor neither sees nor evaluates the manuscript.

The double-blind rule is checked on the serialized JSON text, so a leak
under any key name would fail too.
"""

from __future__ import annotations

import json

import pytest
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.reviews.models import Assignment
from apps.reviews.permissions import IsActiveAssignedReviewer, IsAssignedReviewer
from apps.reviews.serializers import ReviewerManuscriptSerializer, ReviewerVersionSerializer
from tests.factories import (
    AssignmentFactory,
    ManuscriptAuthorFactory,
    ManuscriptFactory,
    ManuscriptVersionFactory,
    UserFactory,
)

AUTHOR_NAME = "Ana Autora Reservada"
AUTHOR_EMAIL = "ana.autora@otra.edu"
AUTHOR_AFFILIATION = "Universidad Secreta"
ORIGINAL_FILENAME = "ana-autora-articulo-final.pdf"


def make_assignment(reviewer=None, **manuscript_values) -> Assignment:
    """An assignment whose manuscript has a known, identifiable author."""
    manuscript = ManuscriptFactory(
        status="UNDER_REVIEW", created_by=UserFactory(), **manuscript_values
    )
    ManuscriptAuthorFactory(
        manuscript=manuscript,
        full_name=AUTHOR_NAME,
        email=AUTHOR_EMAIL,
        affiliation=AUTHOR_AFFILIATION,
        is_corresponding=True,
        author_order=1,
    )
    version = ManuscriptVersionFactory(
        manuscript=manuscript,
        submitted_by=manuscript.created_by,
        original_filename=ORIGINAL_FILENAME,
        metadata_snapshot={"authors": [{"full_name": AUTHOR_NAME, "email": AUTHOR_EMAIL}]},
    )
    return AssignmentFactory(
        manuscript=manuscript, version=version, reviewer=reviewer or UserFactory()
    )


@pytest.mark.django_db
class TestForReviewerScope:
    def test_returns_only_the_reviewers_own_assignments(self) -> None:
        reviewer = UserFactory()
        own = make_assignment(reviewer)
        make_assignment()

        assert list(Assignment.objects.for_reviewer(reviewer)) == [own]

    def test_a_foreign_assignment_is_not_reachable(self) -> None:
        reviewer = UserFactory()
        foreign = make_assignment()

        with pytest.raises(Http404):
            get_object_or_404(Assignment.objects.for_reviewer(reviewer), pk=foreign.pk)

    def test_a_withdrawn_manuscript_is_not_reachable(self) -> None:
        reviewer = UserFactory()
        assignment = make_assignment(
            reviewer, is_active=False, withdrawn_at=timezone.now()
        )

        assert not Assignment.objects.for_reviewer(reviewer).filter(pk=assignment.pk).exists()

    @pytest.mark.parametrize(
        "status",
        [Assignment.Status.ACTIVE, Assignment.Status.COMPLETED],
    )
    def test_active_and_completed_assignments_are_in_scope(self, status) -> None:
        reviewer = UserFactory()
        assignment = make_assignment(reviewer)
        Assignment.objects.filter(pk=assignment.pk).update(status=status)

        assert Assignment.objects.for_reviewer(reviewer).filter(pk=assignment.pk).exists()

    def test_the_scope_loads_manuscript_and_version_in_one_query(
        self, django_assert_num_queries
    ) -> None:
        reviewer = UserFactory()
        make_assignment(reviewer)

        with django_assert_num_queries(1):
            assignment = Assignment.objects.for_reviewer(reviewer).get()
            _ = (assignment.manuscript.code, assignment.version.version_number)

    def test_a_reviewer_who_registered_the_manuscript_does_not_see_it(self) -> None:
        reviewer = UserFactory()
        assignment = make_assignment(reviewer)
        type(assignment.manuscript).objects.filter(pk=assignment.manuscript_id).update(
            created_by=reviewer
        )

        assert not Assignment.objects.for_reviewer(reviewer).exists()

    def test_a_reviewer_who_is_a_linked_coauthor_does_not_see_it(self) -> None:
        reviewer = UserFactory()
        assignment = make_assignment(reviewer)
        ManuscriptAuthorFactory(
            manuscript=assignment.manuscript, user=reviewer, author_order=2
        )

        assert not Assignment.objects.for_reviewer(reviewer).exists()

    def test_a_reviewer_who_is_a_coauthor_by_email_does_not_see_it(self) -> None:
        reviewer = UserFactory(email="Revisor.Coautor@unl.edu.ec")
        assignment = make_assignment(reviewer)
        ManuscriptAuthorFactory(
            manuscript=assignment.manuscript,
            email="revisor.coautor@UNL.edu.ec",
            author_order=2,
        )

        assert not Assignment.objects.for_reviewer(reviewer).exists()

    def test_a_coauthored_manuscript_does_not_hide_the_other_assignments(self) -> None:
        reviewer = UserFactory()
        hidden = make_assignment(reviewer)
        ManuscriptAuthorFactory(manuscript=hidden.manuscript, user=reviewer, author_order=2)
        visible = make_assignment(reviewer)

        assert list(Assignment.objects.for_reviewer(reviewer)) == [visible]

    def test_several_authors_do_not_duplicate_the_row(self) -> None:
        reviewer = UserFactory()
        assignment = make_assignment(reviewer)
        ManuscriptAuthorFactory(manuscript=assignment.manuscript, author_order=2)
        ManuscriptAuthorFactory(manuscript=assignment.manuscript, author_order=3)

        assert Assignment.objects.for_reviewer(reviewer).count() == 1


@pytest.mark.django_db
class TestReviewerSerializers:
    MANUSCRIPT_FIELDS = {
        "id",
        "code",
        "title",
        "abstract",
        "keywords",
        "area",
        "language",
        "current_round",
        "current_version",
    }
    VERSION_FIELDS = {"version_number", "round_number", "submitted_at"}
    FORBIDDEN_KEYS = {
        "authors",
        "email",
        "affiliation",
        "created_by",
        "submitted_by",
        "metadata_snapshot",
        "metadata_sha256",
        "original_filename",
        "original_file_path",
        "original_sha256",
        "original_size_bytes",
        "sanitized_file_path",
        "sanitized_sha256",
        "status",
        "reviewer",
    }

    def test_the_manuscript_payload_is_exactly_the_allowlist(self) -> None:
        assignment = make_assignment()

        data = ReviewerManuscriptSerializer(assignment.manuscript).data

        assert set(data) == self.MANUSCRIPT_FIELDS
        assert data["code"] == assignment.manuscript.code
        assert data["keywords"] == ["clima", "cultivos"]

    def test_the_version_payload_is_exactly_the_allowlist(self) -> None:
        assignment = make_assignment()

        data = ReviewerVersionSerializer(assignment.version).data

        assert set(data) == self.VERSION_FIELDS
        assert data["version_number"] == 1
        assert data["round_number"] == 0

    def test_no_forbidden_key_is_present(self) -> None:
        assignment = make_assignment()

        manuscript = ReviewerManuscriptSerializer(assignment.manuscript).data
        version = ReviewerVersionSerializer(assignment.version).data

        assert not (self.FORBIDDEN_KEYS & set(manuscript))
        assert not (self.FORBIDDEN_KEYS & set(version))

    def test_no_identifying_value_leaks_under_any_key(self) -> None:
        assignment = make_assignment()
        author_login = assignment.manuscript.created_by.email

        text = json.dumps(
            {
                "manuscript": ReviewerManuscriptSerializer(assignment.manuscript).data,
                "version": ReviewerVersionSerializer(assignment.version).data,
            },
            default=str,
        )

        for secret in (
            AUTHOR_NAME,
            AUTHOR_EMAIL,
            AUTHOR_AFFILIATION,
            ORIGINAL_FILENAME,
            author_login,
            "original.pdf",
            "sanitized.pdf",
            "a" * 64,
        ):
            assert secret not in text

    def test_serializers_are_read_only(self) -> None:
        for serializer in (ReviewerManuscriptSerializer, ReviewerVersionSerializer):
            fields = serializer().fields
            assert all(field.read_only for field in fields.values())


def request_as(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


@pytest.mark.django_db
class TestAssignedReviewerPermission:
    def test_the_owner_of_an_active_assignment_passes(self) -> None:
        assignment = make_assignment()

        assert IsAssignedReviewer().has_object_permission(
            request_as(assignment.reviewer), None, assignment
        )

    def test_the_owner_of_a_completed_assignment_passes_but_cannot_download(self) -> None:
        assignment = make_assignment()
        Assignment.objects.filter(pk=assignment.pk).update(status="COMPLETED")
        assignment.refresh_from_db()
        request = request_as(assignment.reviewer)

        assert IsAssignedReviewer().has_object_permission(request, None, assignment)
        with pytest.raises(Http404):
            IsActiveAssignedReviewer().has_object_permission(request, None, assignment)

    def test_another_reviewer_gets_a_404(self) -> None:
        assignment = make_assignment()

        with pytest.raises(Http404):
            IsAssignedReviewer().has_object_permission(request_as(UserFactory()), None, assignment)

    @pytest.mark.parametrize("status", ["REVOKED", "EXPIRED"])
    def test_a_closed_assignment_gets_a_404(self, status) -> None:
        assignment = make_assignment()
        Assignment.objects.filter(pk=assignment.pk).update(status=status)
        assignment.refresh_from_db()

        with pytest.raises(Http404):
            IsAssignedReviewer().has_object_permission(
                request_as(assignment.reviewer), None, assignment
            )

    def test_a_reviewer_who_is_an_author_cannot_reach_nor_evaluate(self) -> None:
        """The scope hides the assignment, so no object ever reaches the permission."""
        reviewer = UserFactory()
        assignment = make_assignment(reviewer)
        ManuscriptAuthorFactory(manuscript=assignment.manuscript, user=reviewer, author_order=2)

        with pytest.raises(Http404):
            get_object_or_404(Assignment.objects.for_reviewer(reviewer), pk=assignment.pk)
        # The evaluation of the assignment resolves through the same scope.
        assert not Assignment.objects.for_reviewer(reviewer).filter(
            pk=assignment.pk, status=Assignment.Status.ACTIVE
        ).exists()
