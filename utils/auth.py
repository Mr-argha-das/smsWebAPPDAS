from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models.institution import User
from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    to_encode.setdefault("type", "access")
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    try:
        user = User.objects.get(id=user_id, is_active=True)
        return user
    except User.DoesNotExist:
        raise HTTPException(status_code=401, detail="User not found or inactive")


async def get_current_superadmin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Super admin access required")
    return current_user


def resolve_school_access(user: User, school_id: Optional[str]) -> Optional[str]:
    if user.is_superadmin or not getattr(user, 'assigned_school', None):
        return school_id
    assigned_school_id = str(user.assigned_school.id)
    if school_id and school_id != assigned_school_id:
        raise HTTPException(status_code=403, detail="Access denied for this school")
    return assigned_school_id


def resolve_branch_scope(user: User, requested_branch_code: Optional[str] = None) -> Optional[str]:
    if user.is_superadmin:
        return requested_branch_code
    assigned_branch_code = getattr(user, 'assigned_branch_code', None)
    allowed_branch_codes = list(getattr(user, 'allowed_branch_codes', []) or [])
    if assigned_branch_code:
        if requested_branch_code and requested_branch_code != assigned_branch_code:
            raise HTTPException(status_code=403, detail="Access denied for this branch")
        return assigned_branch_code
    if allowed_branch_codes:
        if requested_branch_code and requested_branch_code not in allowed_branch_codes:
            raise HTTPException(status_code=403, detail="Access denied for this branch")
        return requested_branch_code or allowed_branch_codes[0]
    return requested_branch_code


def check_permission(user: User, module: str, action: str = "view") -> bool:
    if user.is_superadmin:
        return True
    if not user.role:
        return False
    for perm in user.role.permissions:
        if perm.module == module:
            return getattr(perm, f"can_{action}", False)
    return False


def require_permission(module: str, action: str = "view"):
    async def permission_checker(current_user: User = Depends(get_current_user)):
        if not check_permission(current_user, module, action):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {action} on {module}"
            )
        return current_user
    return permission_checker
