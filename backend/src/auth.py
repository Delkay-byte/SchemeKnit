"""
SchemeKnit Authentication

JWT-based authentication with password hashing and role-based authorization.
"""

from datetime import datetime, timedelta
from typing import Optional
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db, User, RevokedTokenDB, UserSessionDB

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class _BearerUnauthorized(HTTPBearer):
    """HTTP Bearer scheme that reports missing credentials as 401.

    FastAPI's default ``HTTPBearer`` raises 403 for a missing Authorization
    header. Missing authentication is not an authorization decision: the
    correct contract is ``401 Unauthorized`` with a ``WWW-Authenticate``
    challenge. Invalid, expired and revoked tokens already raise 401 in
    ``_authenticate_user``; this makes the missing-credential case consistent.
    """

    async def __call__(self, request: Request):
        try:
            return await super().__call__(request)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            raise


security = _BearerUnauthorized()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    # Note: the ``pwv`` (password-version) claim is only present when the
    # caller supplies it (see create_user_token). Tokens without it are
    # legacy and pass the session-invalidation check unchecked.
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _password_version(user: User) -> int:
    """Unix timestamp (microsecond resolution) of the user's last password change.

    Microsecond resolution is used so that a password change immediately after
    token issuance (e.g., in rapid tests) still produces a distinct version
    and correctly invalidates the older token.
    """
    if user.password_changed_at is None:
        return 0
    return int(user.password_changed_at.timestamp() * 1_000_000)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _authenticate_user(credentials: HTTPAuthorizationCredentials, db: Session) -> User:
    """Shared authentication logic."""
    token = credentials.credentials
    payload = decode_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Session invalidation: reject tokens issued before the last password
    # change/reset. Legacy tokens without a ``pwv`` claim pass through.
    token_pwv = payload.get("pwv")
    if token_pwv is not None and token_pwv != _password_version(user):
        raise HTTPException(
            status_code=401,
            detail="Your session has expired because your password changed. Please sign in again.",
        )

    # Logout revocation: a token explicitly signed out on this server is
    # rejected until its natural expiry. Only the token id is stored.
    jti = payload.get("jti")
    if jti:
        revoked = (
            db.query(RevokedTokenDB)
            .filter(
                RevokedTokenDB.jti == jti,
                RevokedTokenDB.expires_at > datetime.utcnow(),
            )
            .first()
        )
        if revoked is not None:
            raise HTTPException(
                status_code=401,
                detail="You have signed out. Please sign in again.",
            )

        # New sessions are server-verifiable: idle, absolute and revoke-all
        # checks. Tokens issued before this table existed have no row and keep
        # working until their JWT expiry (legacy compatibility).
        session = db.query(UserSessionDB).filter(
            UserSessionDB.jti == jti).first()
        if session is not None:
            now = datetime.utcnow()
            if session.revoked_at is not None:
                raise HTTPException(
                    status_code=401,
                    detail="This session has ended. Please sign in again.",
                )
            if session.expires_at <= now:
                raise HTTPException(
                    status_code=401,
                    detail="Your session has expired. Please sign in again.",
                )
            idle_limit = timedelta(
                minutes=max(1, int(getattr(settings, "SESSION_IDLE_MINUTES", 30)))
            )
            if now - session.last_seen_at > idle_limit:
                raise HTTPException(
                    status_code=401,
                    detail="Your session expired after inactivity. Please sign in again.",
                )
            # Throttle writes: one touch per minute is enough for a 30-minute
            # idle window and avoids a DB write on every request.
            if (now - session.last_seen_at).total_seconds() >= 60:
                session.last_seen_at = now
                db.commit()

    return user


def create_user_token(user: User, expires_delta: Optional[timedelta] = None,
                      jti: Optional[str] = None) -> str:
    """Create a JWT for ``user`` stamped with the current password version.

    Each token carries a unique ``jti`` so logout/revoke-all can invalidate the
    server-side session without affecting other devices.
    """
    return create_access_token(
        {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "pwv": _password_version(user),
            "jti": jti or uuid.uuid4().hex,
        },
        expires_delta=expires_delta,
    )


def create_session_record(db: Session, user_id: str, jti: str) -> UserSessionDB:
    """Create the server-side row for a newly issued login token."""
    now = datetime.utcnow()
    row = UserSessionDB(
        jti=jti,
        user_id=user_id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(
            hours=max(1, int(getattr(settings, "SESSION_ABSOLUTE_HOURS", 12)))
        ),
    )
    db.add(row)
    db.commit()
    return row


def revoke_user_sessions(db: Session, user_id: str,
                         except_jti: Optional[str] = None) -> int:
    """Revoke all active sessions for a user, optionally keeping the current one."""
    now = datetime.utcnow()
    query = db.query(UserSessionDB).filter(
        UserSessionDB.user_id == user_id,
        UserSessionDB.revoked_at.is_(None),
    )
    if except_jti:
        query = query.filter(UserSessionDB.jti != except_jti)
    count = query.update({UserSessionDB.revoked_at: now},
                         synchronize_session=False)
    db.commit()
    return int(count or 0)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    return _authenticate_user(credentials, db)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub")
        if user_id:
            return db.query(User).filter(User.id == user_id).first()
    except Exception:
        pass
    return None


def mfa_enrollment_required(user: User) -> bool:
    """True when a platform admin must enroll before privileged use.

    Platform admins also satisfy the school-admin dependencies (``is_admin``),
    so every privileged dependency consults this helper, not just
    ``require_platform_admin``. DEBUG keeps the local fixture set working.
    """
    return (
        user.role == "platform_admin"
        and not settings.DEBUG
        and not user.mfa_enabled
    )


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Require school-level admin (backward compatible with is_admin)."""
    user = _authenticate_user(credentials, db)
    if not user.is_admin and user.role != "school_admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if mfa_enrollment_required(user):
        raise HTTPException(
            status_code=403,
            detail="MFA enrollment is required before privileged administration.",
        )
    return user


async def require_platform_admin_unenrolled(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Platform-admin identity without requiring MFA enrollment.

    Used only for the MFA status/setup/verify endpoints so an admin can enroll.
    """
    user = _authenticate_user(credentials, db)
    if user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Platform administrator access required")
    return user


async def require_platform_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
    request: Request = None,
) -> User:
    """Require platform-level admin; every request requires enrolled MFA.

    Enrollment is not optional for a platform administrator. When DEBUG is
    off, an unenrolled admin is refused here for reads as well as writes, so a
    direct API call cannot bypass the console's enrollment gate. The only
    pre-enrollment surfaces are ``require_platform_admin_unenrolled`` routes
    under ``/api/auth/mfa``.

    In local DEBUG, enforcement is skipped for the existing test fixture set;
    production runs with DEBUG=false and enforces it.
    """
    user = _authenticate_user(credentials, db)
    if user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Platform administrator access required")
    if not settings.DEBUG and not user.mfa_enabled:
        raise HTTPException(
            status_code=403,
            detail="MFA enrollment is required before privileged administration.",
        )
    return user


def require_school_membership(school_id: str):
    """Dependency factory that checks if user belongs to the specified school."""
    async def _check(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db),
    ) -> User:
        user = _authenticate_user(credentials, db)
        # Platform admins bypass school membership check, but not MFA.
        if user.role == "platform_admin":
            if mfa_enrollment_required(user):
                raise HTTPException(
                    status_code=403,
                    detail="MFA enrollment is required before privileged administration.",
                )
            return user
        # School admins and teachers must belong to the school
        if user.school_id != school_id:
            from .database import SchoolMembershipDB
            membership = db.query(SchoolMembershipDB).filter(
                SchoolMembershipDB.user_id == user.id,
                SchoolMembershipDB.school_id == school_id,
                SchoolMembershipDB.status == "active",
            ).first()
            if not membership:
                raise HTTPException(status_code=403, detail="Not a member of this school")
        return user
    return _check


async def require_teacher_workflow(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency for TEACHER WORKFLOW actions (upload scheme, review/approve,
    generate, edit lessons, exports).

    Architecture lock: Platform Admin is a business/commercial role and must not
    use the teacher lesson-planning workflow. School admins and teachers use it
    (subject to the license check below). Read-only metadata endpoints stay open
    so platform admin can inspect schools without impersonating a teacher.
    """
    user = _authenticate_user(credentials, db)

    if user.role == "platform_admin":
        raise HTTPException(
            status_code=403,
            detail="Platform administrators do not use the teacher lesson-planning workflow",
        )

    # License check for school users (same rules as require_valid_license)
    if not user.school_id:
        return user

    from .database import SchoolLicenseDB
    from datetime import date

    license = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.school_id == user.school_id,
        SchoolLicenseDB.status == "active",
    ).first()

    if not license:
        raise HTTPException(
            status_code=403,
            detail="No active license found for your school. Contact SchemeKnit to activate your license.",
        )

    if license.expiry_date and license.expiry_date < date.today():
        raise HTTPException(
            status_code=403,
            detail="Your SchemeKnit license has expired. Contact SchemeKnit to renew.",
        )

    return user


async def require_valid_license(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency that checks the user's school has an active, non-expired license.
    Platform admins bypass this check.
    Teachers and school admins with expired/suspended licenses get 403.
    Users without a school (no license required for free tier) pass through.
    """
    user = _authenticate_user(credentials, db)

    # Platform admins bypass license check, but not MFA enrollment.
    if user.role == "platform_admin":
        if mfa_enrollment_required(user):
            raise HTTPException(
                status_code=403,
                detail="MFA enrollment is required before privileged administration.",
            )
        return user

    # Users without a school_id are on free tier (no license needed)
    if not user.school_id:
        return user

    from .database import SchoolLicenseDB
    from datetime import date

    license = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.school_id == user.school_id,
        SchoolLicenseDB.status == "active",
    ).first()

    if not license:
        raise HTTPException(
            status_code=403,
            detail="No active license found for your school. Contact SchemeKnit to activate your license.",
        )

    if license.expiry_date and license.expiry_date < date.today():
        raise HTTPException(
            status_code=403,
            detail="Your SchemeKnit license has expired. Contact SchemeKnit to renew.",
        )

    return user
