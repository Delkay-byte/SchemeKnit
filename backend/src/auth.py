"""
SchemeKnit Authentication

JWT-based authentication with password hashing and role-based authorization.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db, User

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


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
    except JWTError:
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

    return user


def create_user_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT for ``user`` stamped with the current password version."""
    return create_access_token(
        {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "pwv": _password_version(user),
        },
        expires_delta=expires_delta,
    )


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


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Require school-level admin (backward compatible with is_admin)."""
    user = _authenticate_user(credentials, db)
    if not user.is_admin and user.role != "school_admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_platform_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Require platform-level admin. Only platform_admin role."""
    user = _authenticate_user(credentials, db)
    if user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Platform administrator access required")
    return user


def require_school_membership(school_id: str):
    """Dependency factory that checks if user belongs to the specified school."""
    async def _check(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db),
    ) -> User:
        user = _authenticate_user(credentials, db)
        # Platform admins bypass school membership check
        if user.role == "platform_admin":
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

    # Platform admins bypass license check
    if user.role == "platform_admin":
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
