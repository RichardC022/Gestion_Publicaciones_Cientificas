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
"""

from __future__ import annotations

from collections import namedtuple
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import (
    RevocationReason,
    User,
    UserRole,
    RefreshToken as RefreshTokenRecord,
)
from config.exceptions import DomainError, ErrorCode

#: Respuesta única ante credenciales inválidas, cuenta inexistente o cuenta
#: deshabilitada (plan §6.1). Nunca se revela la causa exacta.
GENERIC_AUTH_MESSAGE = "Credenciales institucionales inválidas."

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
