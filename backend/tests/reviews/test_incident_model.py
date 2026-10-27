"""Tests for the confidential incident report model (TSK-59).

Covers the acceptance criteria: only one ``OPEN`` report per assignment;
a ``RESOLVED`` report requires ``resolution`` and ``resolved_at``; and
creating a report does not change the PDF, the evaluation or the
manuscript status.

The constraints are exercised with queryset operations, so the database
answers and not a guard of the model. The ``409`` of the second open
report arrives with the endpoints (TSK-60 onwards).
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.publications.models import Manuscript
from apps.reviews.models import Assignment, IncidentReport
from tests.factories import (
    AssignmentFactory,
    CorrectionRoundFactory,
    EvaluationFactory,
    IncidentReportFactory,
    UserFactory,
)


@pytest.mark.django_db
class TestIncidentDefaults:
    def test_a_new_report_is_open_and_unresolved(self) -> None:
        incident = IncidentReportFactory()

        incident.refresh_from_db()
        assert incident.status == IncidentReport.Status.OPEN
        assert incident.resolution is None
        assert incident.resolved_at is None
        assert incident.resolved_by is None
        assert incident.correction_round is None
        assert incident.created_at is not None

    def test_the_report_is_reachable_from_its_assignment(self) -> None:
        incident = IncidentReportFactory()

        assert list(incident.assignment.incident_reports.all()) == [incident]


@pytest.mark.django_db
class TestIncidentChoices:
    def test_an_unknown_report_type_is_rejected(self) -> None:
        with pytest.raises(IntegrityError, match="ck_incident_report_type"):
            with transaction.atomic():
                IncidentReportFactory(report_type="SPAM")

    def test_other_is_a_valid_report_type(self) -> None:
        incident = IncidentReportFactory(report_type=IncidentReport.ReportType.OTHER)

        assert incident.report_type == "OTHER"

    def test_an_unknown_status_is_rejected(self) -> None:
        # Con resolución y fecha completas, solo `ck_incident_status` puede fallar.
        with pytest.raises(IntegrityError, match="ck_incident_status"):
            with transaction.atomic():
                IncidentReportFactory(
                    status="CLOSED",
                    resolution=IncidentReport.Resolution.DISMISS,
                    resolved_at=timezone.now(),
                )

    def test_an_unknown_resolution_is_rejected(self) -> None:
        with pytest.raises(IntegrityError, match="ck_incident_resolution"):
            with transaction.atomic():
                IncidentReportFactory(
                    status=IncidentReport.Status.RESOLVED,
                    resolution="IGNORE",
                    resolved_at=timezone.now(),
                )


@pytest.mark.django_db
class TestResolvedRequirements:
    @pytest.mark.parametrize("resolution", IncidentReport.Resolution.values)
    def test_a_resolved_report_with_resolution_and_date_is_accepted(self, resolution) -> None:
        incident = IncidentReportFactory(
            status=IncidentReport.Status.RESOLVED,
            resolution=resolution,
            resolved_at=timezone.now(),
            resolved_by=UserFactory(),
        )

        assert incident.status == IncidentReport.Status.RESOLVED

    @pytest.mark.parametrize("missing", ["resolution", "resolved_at"])
    def test_a_resolved_report_without_a_required_field_is_rejected(self, missing) -> None:
        values = {
            "status": IncidentReport.Status.RESOLVED,
            "resolution": IncidentReport.Resolution.DISMISS,
            "resolved_at": timezone.now(),
        }
        values[missing] = None

        with pytest.raises(IntegrityError, match="ck_incident_resolved_complete"):
            with transaction.atomic():
                IncidentReportFactory(**values)

    def test_an_open_report_cannot_be_resolved_without_data(self) -> None:
        incident = IncidentReportFactory()

        with pytest.raises(IntegrityError, match="ck_incident_resolved_complete"):
            with transaction.atomic():
                IncidentReport.objects.filter(pk=incident.pk).update(status="RESOLVED")

        incident.refresh_from_db()
        assert incident.status == IncidentReport.Status.OPEN

    def test_resolving_with_all_the_data_succeeds(self) -> None:
        incident = IncidentReportFactory()

        IncidentReport.objects.filter(pk=incident.pk).update(
            status=IncidentReport.Status.RESOLVED,
            resolution=IncidentReport.Resolution.REASSIGN,
            resolved_at=timezone.now(),
        )

        incident.refresh_from_db()
        assert incident.status == IncidentReport.Status.RESOLVED
        assert incident.resolution == IncidentReport.Resolution.REASSIGN


@pytest.mark.django_db
class TestSingleOpenIncident:
    def test_a_second_open_report_for_an_assignment_is_rejected(self) -> None:
        first = IncidentReportFactory()

        with pytest.raises(IntegrityError, match="uq_incident_open"):
            with transaction.atomic():
                IncidentReportFactory(assignment=first.assignment)

    def test_a_new_open_report_is_allowed_after_resolving_the_previous_one(self) -> None:
        first = IncidentReportFactory(
            status=IncidentReport.Status.RESOLVED,
            resolution=IncidentReport.Resolution.DISMISS,
            resolved_at=timezone.now(),
        )

        second = IncidentReportFactory(assignment=first.assignment)

        assert second.status == IncidentReport.Status.OPEN
        assert first.assignment.incident_reports.count() == 2

    def test_several_resolved_reports_can_coexist(self) -> None:
        first = IncidentReportFactory(
            status=IncidentReport.Status.RESOLVED,
            resolution=IncidentReport.Resolution.DISMISS,
            resolved_at=timezone.now(),
        )

        IncidentReportFactory(
            assignment=first.assignment,
            status=IncidentReport.Status.RESOLVED,
            resolution=IncidentReport.Resolution.REASSIGN,
            resolved_at=timezone.now(),
        )

        assert first.assignment.incident_reports.count() == 2

    def test_two_assignments_can_each_have_an_open_report(self) -> None:
        IncidentReportFactory()
        IncidentReportFactory()

        assert IncidentReport.objects.filter(status=IncidentReport.Status.OPEN).count() == 2


@pytest.mark.django_db
class TestReferentialProtection:
    def test_an_assignment_with_a_report_cannot_be_deleted(self) -> None:
        incident = IncidentReportFactory()

        with pytest.raises(ProtectedError):
            incident.assignment.delete()

    def test_a_reporter_with_a_report_cannot_be_deleted(self) -> None:
        incident = IncidentReportFactory()

        with pytest.raises(ProtectedError):
            incident.reporter.delete()

    def test_a_manuscript_with_a_report_cannot_be_deleted(self) -> None:
        incident = IncidentReportFactory()

        with pytest.raises(ProtectedError):
            incident.manuscript.delete()

    def test_a_round_linked_to_a_report_cannot_be_deleted(self) -> None:
        incident = IncidentReportFactory()
        round_ = CorrectionRoundFactory(manuscript=incident.manuscript, round_number=1)
        IncidentReport.objects.filter(pk=incident.pk).update(correction_round=round_)

        with pytest.raises(ProtectedError):
            round_.delete()

    def test_deleting_the_resolver_keeps_the_report(self) -> None:
        resolver = UserFactory()
        incident = IncidentReportFactory(
            status=IncidentReport.Status.RESOLVED,
            resolution=IncidentReport.Resolution.DISMISS,
            resolved_at=timezone.now(),
            resolved_by=resolver,
        )

        resolver.delete()

        incident.refresh_from_db()
        assert incident.resolved_by is None
        assert incident.status == IncidentReport.Status.RESOLVED


@pytest.mark.django_db
class TestReportHasNoSideEffects:
    def test_creating_a_report_leaves_assignment_evaluation_and_manuscript_untouched(
        self,
    ) -> None:
        assignment = AssignmentFactory()
        evaluation = EvaluationFactory(assignment=assignment)
        manuscript = assignment.manuscript
        version = assignment.version
        before = (
            manuscript.status,
            manuscript.updated_at,
            version.original_sha256,
            version.sanitized_sha256,
            version.sanitized_file_path,
            evaluation.status,
            evaluation.updated_at,
            assignment.status,
            assignment.updated_at,
        )

        IncidentReportFactory(assignment=assignment)

        for instance in (manuscript, version, evaluation, assignment):
            instance.refresh_from_db()
        after = (
            manuscript.status,
            manuscript.updated_at,
            version.original_sha256,
            version.sanitized_sha256,
            version.sanitized_file_path,
            evaluation.status,
            evaluation.updated_at,
            assignment.status,
            assignment.updated_at,
        )
        assert after == before
        assert manuscript.status == Manuscript.Status.UNDER_REVIEW
        assert assignment.status == Assignment.Status.ACTIVE
