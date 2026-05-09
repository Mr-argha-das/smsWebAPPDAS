from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from models.institution import User, Role, Permission, School
from utils.auth import (
    verify_password, get_password_hash, create_access_token,
    create_refresh_token, decode_token, get_current_user
)
from utils.helpers import success_response

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    full_name: str
    phone: Optional[str] = None
    is_superadmin: bool = False
    school_id: Optional[str] = None
    assigned_branch_code: Optional[str] = None
    assigned_branch_name: Optional[str] = None
    allowed_branch_codes: Optional[list[str]] = None


class UserManagementRequest(BaseModel):
    email: str
    username: str
    full_name: str
    phone: Optional[str] = None
    password: Optional[str] = None
    is_superadmin: bool = False
    school_id: Optional[str] = None
    role_id: Optional[str] = None
    assigned_branch_code: Optional[str] = None
    allowed_branch_codes: Optional[list[str]] = None
    is_active: bool = True


def _role_name(user: User) -> str:
    return str(user.role.name if user.role else "").strip().lower()


def _can_manage_users(user: User) -> bool:
    if user.is_superadmin:
        return True
    role_name = _role_name(user)
    return any(token in role_name for token in ["admin", "principal", "hr", "super"])


def _ensure_user_management_access(current_user: User) -> None:
    if not _can_manage_users(current_user):
        raise HTTPException(403, "You are not allowed to manage users")


def _resolve_managed_school(current_user: User, school_id: Optional[str]) -> Optional[School]:
    if current_user.is_superadmin:
        if not school_id:
            return None
        try:
            return School.objects.get(id=school_id)
        except School.DoesNotExist:
            raise HTTPException(400, "Assigned school not found")

    assigned_school = getattr(current_user, "assigned_school", None)
    if assigned_school:
        if school_id and str(assigned_school.id) != school_id:
            raise HTTPException(403, "You can only manage users for your assigned school")
        return assigned_school

    if school_id:
        try:
            return School.objects.get(id=school_id)
        except School.DoesNotExist:
            raise HTTPException(400, "Assigned school not found")
    return None


def _school_branch_lookup(school: Optional[School]) -> dict[str, str]:
    if not school:
        return {}
    return {
        str(branch.code or "").strip().upper(): branch.name or branch.code or ""
        for branch in (school.branches or [])
        if branch.code
    }


def _normalize_branch_scope(
    school: Optional[School],
    assigned_branch_code: Optional[str],
    allowed_branch_codes: Optional[list[str]],
) -> tuple[Optional[str], Optional[str], list[str]]:
    assigned_code = str(assigned_branch_code or "").strip().upper()
    allowed_codes = [str(code).strip().upper() for code in (allowed_branch_codes or []) if str(code).strip()]

    if not school:
        if assigned_code or allowed_codes:
            raise HTTPException(400, "Select a school before assigning branch access")
        return None, None, []

    branch_map = _school_branch_lookup(school)
    if not branch_map:
        if assigned_code or allowed_codes:
            raise HTTPException(400, "This school has no branches configured yet")
        return None, None, []

    invalid_codes = [code for code in ([assigned_code] if assigned_code else []) + allowed_codes if code not in branch_map]
    if invalid_codes:
        raise HTTPException(400, f"Unknown branch code(s): {', '.join(invalid_codes)}")

    if assigned_code and assigned_code not in allowed_codes:
        allowed_codes.insert(0, assigned_code)

    deduped_allowed = list(dict.fromkeys(allowed_codes))
    assigned_name = branch_map.get(assigned_code) if assigned_code else None
    return assigned_code or None, assigned_name, deduped_allowed


def _serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "phone": user.phone,
        "is_active": user.is_active,
        "is_superadmin": user.is_superadmin,
        "role_id": str(user.role.id) if user.role else None,
        "role_name": user.role.name if user.role else None,
        "assigned_school_id": str(user.assigned_school.id) if user.assigned_school else None,
        "assigned_school_name": user.assigned_school.name if user.assigned_school else None,
        "assigned_branch_code": user.assigned_branch_code,
        "assigned_branch_name": user.assigned_branch_name,
        "allowed_branch_codes": user.allowed_branch_codes or [],
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.post("/login")
async def login(data: LoginRequest):
    user = User.objects(username=data.username, is_active=True).first()
    if not user:
        user = User.objects(email=data.username, is_active=True).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid username or password")
    user.update(last_login=datetime.utcnow())
    token_data = {"sub": str(user.id), "username": user.username}
    access_token  = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    return success_response({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "is_superadmin": user.is_superadmin,
            "role": str(user.role.id) if user.role else None,
            "role_name": user.role.name if user.role else None,
            "avatar": user.avatar,
            "assigned_school_id": str(user.assigned_school.id) if user.assigned_school else None,
            "assigned_branch_code": user.assigned_branch_code,
            "assigned_branch_name": user.assigned_branch_name,
            "allowed_branch_codes": user.allowed_branch_codes or [],
            "permissions": [
                {
                    "module": permission.module,
                    "can_view": permission.can_view,
                    "can_create": permission.can_create,
                    "can_edit": permission.can_edit,
                    "can_delete": permission.can_delete
                }
                for permission in (user.role.permissions if user.role else [])
            ]
        }
    }, "Login successful")


@router.post("/register")
async def register(data: RegisterRequest):
    if User.objects(username=data.username).first():
        raise HTTPException(400, "Username already taken")
    if User.objects(email=data.email).first():
        raise HTTPException(400, "Email already registered")
    user = User(
        email=data.email,
        username=data.username,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        phone=data.phone,
        is_superadmin=data.is_superadmin,
        assigned_branch_code=data.assigned_branch_code,
        assigned_branch_name=data.assigned_branch_name,
        allowed_branch_codes=data.allowed_branch_codes or []
    )
    if data.school_id:
        try:
            user.assigned_school = School.objects.get(id=data.school_id)
        except School.DoesNotExist:
            raise HTTPException(400, "Assigned school not found")
    user.save()
    return success_response({"id": str(user.id), "username": user.username, "email": user.email}, "Registered successfully")


@router.post("/refresh")
async def refresh_token(refresh_token: str):
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Invalid refresh token")
    try:
        user = User.objects.get(id=payload.get("sub"), is_active=True)
    except User.DoesNotExist:
        raise HTTPException(401, "User not found")
    token_data = {"sub": str(user.id), "username": user.username}
    return success_response({"access_token": create_access_token(token_data), "token_type": "bearer"})


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return success_response({
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "phone": current_user.phone,
        "is_superadmin": current_user.is_superadmin,
        "role": current_user.role.name if current_user.role else None,
        "avatar": current_user.avatar,
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
        "assigned_school_id": str(current_user.assigned_school.id) if current_user.assigned_school else None,
        "assigned_branch_code": current_user.assigned_branch_code,
        "assigned_branch_name": current_user.assigned_branch_name,
        "allowed_branch_codes": current_user.allowed_branch_codes or [],
        "permissions": [
            {
                "module": permission.module,
                "can_view": permission.can_view,
                "can_create": permission.can_create,
                "can_edit": permission.can_edit,
                "can_delete": permission.can_delete
            }
            for permission in (current_user.role.permissions if current_user.role else [])
        ]
    })


@router.put("/me/change-password")
async def change_password(old_password: str, new_password: str, current_user: User = Depends(get_current_user)):
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(400, "Old password is incorrect")
    if len(new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    current_user.update(hashed_password=get_password_hash(new_password))
    return success_response(message="Password changed successfully")


@router.post("/roles")
async def create_role(data: dict, current_user: User = Depends(get_current_user)):
    if not current_user.is_superadmin:
        raise HTTPException(403, "Only superadmin can create roles")
    if Role.objects(name=data['name']).first():
        raise HTTPException(400, "Role already exists")
    role = Role(name=data['name'], description=data.get('description'))
    for perm in data.get('permissions', []):
        role.permissions.append(Permission(**perm))
    role.save()
    return success_response({"id": str(role.id), "name": role.name}, "Role created")


@router.get("/roles")
async def list_roles(current_user: User = Depends(get_current_user)):
    roles = Role.objects.all()
    return success_response([{
        "id": str(r.id), "name": r.name, "description": r.description, "is_system": r.is_system,
        "permissions": [{"module": p.module, "can_view": p.can_view, "can_create": p.can_create, "can_edit": p.can_edit, "can_delete": p.can_delete} for p in r.permissions]
    } for r in roles])


@router.get("/users")
async def list_users(
    school_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    _ensure_user_management_access(current_user)
    managed_school = _resolve_managed_school(current_user, school_id)

    query = User.objects.order_by("-created_at")
    if managed_school:
        query = query.filter(assigned_school=managed_school)
    elif not current_user.is_superadmin and getattr(current_user, "assigned_school", None):
        query = query.filter(assigned_school=current_user.assigned_school)

    return success_response([_serialize_user(user) for user in query])


@router.post("/users")
async def create_user_account(
    data: UserManagementRequest,
    current_user: User = Depends(get_current_user),
):
    _ensure_user_management_access(current_user)
    if not data.password or len(data.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if User.objects(username=data.username).first():
        raise HTTPException(400, "Username already taken")
    if User.objects(email=data.email).first():
        raise HTTPException(400, "Email already registered")

    managed_school = _resolve_managed_school(current_user, data.school_id)
    normalized_branch_code, normalized_branch_name, normalized_allowed_codes = _normalize_branch_scope(
        managed_school,
        data.assigned_branch_code,
        data.allowed_branch_codes,
    )

    role = None
    if data.role_id:
        role = Role.objects(id=data.role_id).first()
        if not role:
            raise HTTPException(400, "Selected role not found")

    user = User(
        email=data.email.strip(),
        username=data.username.strip(),
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name.strip(),
        phone=(data.phone or "").strip() or None,
        is_superadmin=bool(data.is_superadmin),
        is_active=bool(data.is_active),
        assigned_school=managed_school,
        assigned_branch_code=normalized_branch_code,
        assigned_branch_name=normalized_branch_name,
        allowed_branch_codes=normalized_allowed_codes,
        role=role,
    )
    user.save()
    return success_response(_serialize_user(user), "User created successfully")


@router.put("/users/{user_id}")
async def update_user_account(
    user_id: str,
    data: UserManagementRequest,
    current_user: User = Depends(get_current_user),
):
    _ensure_user_management_access(current_user)
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise HTTPException(404, "User not found")

    managed_school = _resolve_managed_school(current_user, data.school_id)
    if not current_user.is_superadmin and getattr(current_user, "assigned_school", None):
        user_school_id = str(user.assigned_school.id) if user.assigned_school else None
        current_school_id = str(current_user.assigned_school.id)
        if user_school_id and user_school_id != current_school_id:
            raise HTTPException(403, "You can only update users from your assigned school")

    duplicate_username = User.objects(username=data.username.strip(), id__ne=user.id).first()
    if duplicate_username:
        raise HTTPException(400, "Username already taken")
    duplicate_email = User.objects(email=data.email.strip(), id__ne=user.id).first()
    if duplicate_email:
        raise HTTPException(400, "Email already registered")

    normalized_branch_code, normalized_branch_name, normalized_allowed_codes = _normalize_branch_scope(
        managed_school,
        data.assigned_branch_code,
        data.allowed_branch_codes,
    )

    role = None
    if data.role_id:
        role = Role.objects(id=data.role_id).first()
        if not role:
            raise HTTPException(400, "Selected role not found")

    user.email = data.email.strip()
    user.username = data.username.strip()
    user.full_name = data.full_name.strip()
    user.phone = (data.phone or "").strip() or None
    user.is_superadmin = bool(data.is_superadmin)
    user.is_active = bool(data.is_active)
    user.assigned_school = managed_school
    user.assigned_branch_code = normalized_branch_code
    user.assigned_branch_name = normalized_branch_name
    user.allowed_branch_codes = normalized_allowed_codes
    user.role = role
    user.updated_at = datetime.utcnow()
    if data.password:
        if len(data.password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        user.hashed_password = get_password_hash(data.password)
    user.save()
    return success_response(_serialize_user(user), "User updated successfully")
