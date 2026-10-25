"""Institutional authentication and session service (plan sections 2.2 and 6.1).

Responsibilities:

* Validate institutional credentials without ever revealing whether the
  account does not exist, is inactive or the password was wrong: all
  failures answer with :data:`GENERIC_AUTH_MESSAGE` and ``AUTH_INVALID``.
* Issue access + refresh pairs signed with SimpleJWT and register every
  refresh token in ``users_refresh_token``. The library only signs; the
  domain decides validity: single-use rotation, logout revocation and the
  institutional idle window live in the table.
* Re-read the active roles from PostgreSQL on every session operation. The
  ``roles`` claim embedded in the token is a hint for the interface, never
  an authorization source (plan section 2.9).
* Rate limit the login (TSK-20, plan section 6.1): after five failed
  attempts for an identifier in fifteen minutes the sixth attempt answers
  ``429`` with ``Retry-After`` — checked before credential validation, so
  the lock never reveals whether the account exists. The block expires by
  itself when the failures age out of the window.
* Audit every login flow event — success, failure and block — with the
  attempted identifier, IP and result, never the password. If the audit
  trail cannot be written the login fails closed with ``503``.
"""

from __future__ import annotations

from collections import namedtuple
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.audit.services import AuditService, AuditUnavailable
from apps.users.models import (
    RevocationReason,
    User,
    UserRole,
    LoginAttempt,
    RefreshToken as RefreshTokenRecord,
)
from config.exceptions import DomainError, ErrorCode

#: Respuesta única ante credenciales inválidas, cuenta inexistente o cuenta
#: deshabilitada (plan §6.1). Nunca se revela la causa exacta.
GENERIC_AUTH_MESSAGE = "Credenciales institucionales inválidas."

#: Respuesta del bloqueo por intentos excedidos (plan §6.1, TSK-20).
LOCKED_MESSAGE = "Demasiados intentos fallidos. Intente de nuevo en unos minutos."

#: Respuesta cuando la auditoría no puede escribirse: la acción se revierte
#: y se falla cerrado con 503 (plan §6.5).
AUDIT_UNAVAILABLE_MESSAGE = (
    "No se pudo registrar la auditoría de la operación; la acción fue cancelada."
)

#: Límite institucional: cinco fallos por identificador en quince minutos.
LOCKOUT_MAX_FAILURES = 5
LOCKOUT_WINDOW = timedelta(minutes=15)

#: Sesión emitida: tokens y registro de dominio del refresh.
IssuedSession = namedtuple("IssuedSession", ("access", "refresh", "record", "roles"))


def _auth_error() -> DomainError:
    """The generic authentication error; the endpoint never says more."""
    return DomainError(GENERIC_AUTH_MESSAGE, code=ErrorCode.AUTH_INVALID)


class _RefreshRejected(Exception):
    """Internal control flow: a refresh token was rejected.

    Carries the security side effects that must survive even though the
    validation transaction rolls back: revoking the presented record and
    the replacement chain it spawned (reuse detection).
    """

    def __init__(
        self,
        *,
        chain: list[RefreshTokenRecord] = (),
        revoke_record: RefreshTokenRecord | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__("refresh rejected")
        self.chain = list(chain)
        self.revoke_record = revoke_record
        self.reason = reason


def active_role_codes(user: User) -> list[str]:
    """Active role codes, always read from PostgreSQL (never from the JWT)."""
    return list(
        UserRole.objects.filter(user=user, is_active=True)
        .order_by("role_id")
        .values_list("role__code", flat=True)
    )


def authenticate_by_identifier(identifier: str, password: str) -> User | None:
    """Validate institutional credentials without revealing the reason.

    The identifier can be the institutional id, the username or the email
    (case-insensitive). A wrong password, an unknown account and a
    disabled account all return ``None`` so the endpoint answers with the
    same generic message.
    """
    user = (
        User.objects.filter(
            Q(institutional_id__iexact=identifier)
            | Q(username__iexact=identifier)
            | Q(email__iexact=identifier)
        ).first()
    )
    if user is None:
        # Hash fantasma: una cuenta inexistente cuesta el mismo tiempo que
        # una conocida y no permite enumerar cuentas por temporización.
        User().set_password(password)
        return None
    if not user.check_password(password) or not user.is_active:
        return None
    return user


# ---------------------------------------------------------------------------
# Límite de intentos y auditoría de login (TSK-20, plan sections 6.1 and 6.5)
# ---------------------------------------------------------------------------


def normalize_identifier(identifier: str) -> str:
    """Canonical rate-limit key: trimmed and lower cased.

    The institutional id, the username and the email are matched case
    insensitively, so their failures must count towards the same lock.
    """
    return identifier.strip().lower()


def lockout_remaining_seconds(identifier: str) -> int | None:
    """Seconds of lock left, or ``None`` when the identifier is not blocked.

    Blocked := :data:`LOCKOUT_MAX_FAILURES` failed attempts for the
    identifier inside the trailing fifteen-minute window. The lock expires
    by itself when those failures age out of the window; nothing has to be
    cleaned up. Attempts rejected by the block are not counted as new
    failures, so a persistent attacker cannot extend the lock and the
    legitimate user can always return once the window has passed.
    """
    failures = list(
        LoginAttempt.objects.filter(
            identifier=identifier,
            successful=False,
            attempted_at__gte=timezone.now() - LOCKOUT_WINDOW,
        ).order_by("-attempted_at")[:LOCKOUT_MAX_FAILURES]
    )
    if len(failures) < LOCKOUT_MAX_FAILURES:
        return None
    oldest_counted = failures[-1].attempted_at
    remaining = int(
        (oldest_counted + LOCKOUT_WINDOW - timezone.now()).total_seconds()
    )
    return max(remaining, 1)


def _audit_login(
    *,
    result: str,
    reason: str | None = None,
    actor: User | None = None,
    details: dict,
    ip_address: str | None,
    user_agent: str | None,
    request_id: str | None,
) -> None:
    """Append one login-flow audit event; fail closed with ``503``."""
    try:
        with transaction.atomic():
            AuditService.record(
                action="LOGIN",
                entity_type="SESSION",
                result=result,
                actor=actor,
                reason=reason,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
            )
    except AuditUnavailable as exc:
        raise DomainError(
            AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE
        ) from exc


def login(
    identifier: str,
    password: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> IssuedSession:
    """Full institutional login: rate limit, credentials, audit, session.

    Raises:
        DomainError ``AUTH_LOCKED``: ``429`` with ``Retry-After`` when the
            identifier is blocked after five failures in fifteen minutes.
            The check runs before credential validation, so the answer
            never reveals whether the account exists.
        DomainError ``AUTH_INVALID``: ``401`` with the generic message for
            invalid credentials, nonexistent or inactive accounts.
        DomainError ``AUDIT_UNAVAILABLE``: ``503`` when the audit trail
            cannot be written; the session is not issued and the attempt
            is not kept (plan section 6.5).
    """
    identifier = normalize_identifier(identifier)
    details = {"identifier": identifier}

    # 1) Bloqueo por límite de intentos, antes de validar credenciales.
    retry_after = lockout_remaining_seconds(identifier)
    if retry_after is not None:
        _audit_login(
            result=AuditLog.Result.DENIED,
            reason="Límite de intentos de acceso excedido.",
            details={**details, "retry_after": retry_after},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        raise DomainError(
            LOCKED_MESSAGE,
            code=ErrorCode.AUTH_LOCKED,
            headers={"Retry-After": str(retry_after)},
        )

    # 2) Validación de credenciales con respuesta genérica.
    user = authenticate_by_identifier(identifier, password)

    # 3) Intento y auditoría en la misma transacción (plan section 6.5);
    #    la contraseña jamás se persiste.
    try:
        with transaction.atomic():
            LoginAttempt.objects.create(
                identifier=identifier,
                successful=user is not None,
                ip_address=ip_address,
            )
            if user is None:
                AuditService.record(
                    action="LOGIN",
                    entity_type="SESSION",
                    result=AuditLog.Result.FAILURE,
                    reason=GENERIC_AUTH_MESSAGE,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details=details,
                )
            else:
                session = issue_session(user)
                AuditService.record(
                    action="LOGIN",
                    entity_type="SESSION",
                    result=AuditLog.Result.SUCCESS,
                    actor=user,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details=details,
                )
                return session
    except AuditUnavailable as exc:
        raise DomainError(
            AUDIT_UNAVAILABLE_MESSAGE, code=ErrorCode.AUDIT_UNAVAILABLE
        ) from exc

    raise DomainError(GENERIC_AUTH_MESSAGE, code=ErrorCode.AUTH_INVALID)


def issue_session(user: User) -> IssuedSession:
    """Issue an access + refresh pair and register the refresh for control.

    The ``roles`` claim travels in both tokens as a hint for the interface;
    authorization always re-reads PostgreSQL (plan sections 2.9 and 6.1).
    """
    roles = active_role_codes(user)
    refresh = RefreshToken.for_user(user)
    refresh["roles"] = roles
    record = RefreshTokenRecord.objects.create(
        user=user,
        jti=refresh["jti"],
        expires_at=datetime.fromtimestamp(
            refresh["exp"], tz=datetime_timezone.utc
        ),
    )
    return IssuedSession(
        access=str(refresh.access_token),
        refresh=str(refresh),
        record=record,
        roles=roles,
    )


def _decode_refresh(raw_refresh: str) -> RefreshToken:
    """Verify signature, expiry and token type of a refresh token."""
    try:
        # Verifica firma, `exp` y el claim `token_type=refresh`.
        return RefreshToken(raw_refresh)
    except Exception as exc:  # TokenError y errores de decodificación.
        raise _auth_error() from exc


def _chain_from(record: RefreshTokenRecord) -> list[RefreshTokenRecord]:
    """Walk the replacement chain spawned by a consumed token."""
    chain: list[RefreshTokenRecord] = []
    seen = {record.jti}
    current = record
    while current.replaced_by_jti and current.replaced_by_jti not in seen:
        seen.add(current.replaced_by_jti)
        descendant = RefreshTokenRecord.objects.filter(
            jti=current.replaced_by_jti
        ).first()
        if descendant is None:
            break
        chain.append(descendant)
        current = descendant
    return chain


def _rotate(raw_refresh: str) -> IssuedSession:
    """Rotate once inside a serialized transaction; raise on any rejection."""
    token = _decode_refresh(raw_refresh)
    jti = token["jti"]

    with transaction.atomic():
        # select_for_update serializa dos pestañas que refrescan a la vez.
        record = (
            RefreshTokenRecord.objects.select_for_update()
            .select_related("user")
            .filter(jti=jti)
            .first()
        )
        if record is None:
            # Firma válida pero no está en el registro: no lo emitimos
            # nosotros o ya fue depurado.
            raise _auth_error()
        if record.revoked_at is not None:
            # Reutilización de un token ya consumido: se rechaza y la
            # cadena de reemplazos muere con él.
            raise _RefreshRejected(chain=_chain_from(record))

        now = timezone.now()
        if record.expires_at <= now:
            raise _auth_error()
        if not record.user.is_active:
            # Estado de la cuenta releído de PostgreSQL en cada solicitud.
            raise _RefreshRejected(
                chain=_chain_from(record),
                revoke_record=record,
                reason=RevocationReason.ACCOUNT_DISABLED,
            )
        last_activity = record.last_used_at or record.issued_at
        idle_limit = timedelta(minutes=settings.SESSION_IDLE_MINUTES)
        if now - last_activity > idle_limit:
            # Ventana de inactividad institucional (plan §6.1).
            raise _RefreshRejected(
                chain=_chain_from(record),
                revoke_record=record,
                reason=RevocationReason.IDLE_TIMEOUT,
            )

        session = issue_session(record.user)
        record.revoke(
            reason=RevocationReason.ROTATED,
            replaced_by_jti=session.record.jti,
            last_used_at=now,
        )
        return session


def rotate(raw_refresh: str) -> IssuedSession:
    """Rotate a refresh token: single-use, DB-validated, idle-controlled."""
    try:
        return _rotate(raw_refresh)
    except _RefreshRejected as rejected:
        # Los efectos de seguridad se confirman en su propia transacción:
        # la transacción de validación se revirtió al lanzar la excepción.
        with transaction.atomic():
            if rejected.revoke_record is not None:
                rejected.revoke_record.revoke(reason=rejected.reason)
            for descendant in rejected.chain:
                descendant.revoke(reason=RevocationReason.REUSE)
        raise _auth_error() from None


def revoke_current(raw_refresh: str, *, reason: str) -> RefreshTokenRecord | None:
    """Revoke the refresh token carried by the cookie (logout).

    Returns the revoked record, or ``None`` when the cookie no longer
    carries a decodable token: there is nothing vigente to revoke and the
    cookie is cleared anyway.
    """
    try:
        token = RefreshToken(raw_refresh)
    except Exception:
        return None
    record = RefreshTokenRecord.objects.filter(jti=token["jti"]).first()
    if record is None:
        return None
    record.revoke(reason=reason)
    return record
