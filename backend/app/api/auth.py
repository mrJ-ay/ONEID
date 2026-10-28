from __future__ import annotations

import base64
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Header, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from pwdlib import PasswordHash

from app.config import get_settings
from app.database import get_connection

router = APIRouter(prefix="/api")
settings = get_settings()
password_hash = PasswordHash.recommended()


# --------------------------------------------------
# Request models
# --------------------------------------------------

class RegisterInput(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    nickname: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class RoleInput(BaseModel):
    role: Literal["user", "admin"]


class OAuthAuthorizeInput(BaseModel):
    client_id: str = Field(min_length=2, max_length=64)
    redirect_uri: str = Field(min_length=1, max_length=2048)
    code_challenge: str = Field(min_length=43, max_length=128)
    state: str = Field(min_length=16, max_length=256)


class OAuthTokenInput(BaseModel):
    client_id: str
    redirect_uri: str
    code: str
    code_verifier: str = Field(min_length=43, max_length=128)


class GlobalSuspensionInput(BaseModel):
    suspended: bool
    reason: str | None = Field(default=None, max_length=500)


class SiteSuspensionInput(BaseModel):
    suspended: bool
    reason: str | None = Field(default=None, max_length=500)


# --------------------------------------------------
# Utilities
# --------------------------------------------------

def normalize_username(value: str) -> str:
    return value.strip().casefold()


def validate_username(value: str) -> str:
    username = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", username):
        raise HTTPException(
            status_code=422,
            detail="사용자명은 영문, 숫자, 밑줄, 마침표, 하이픈으로 2~32자여야 합니다.",
        )
    return username


def public_user(row: Any) -> dict[str, Any]:
    role = row["role"]
    return {
        "id": row["user_id"],
        "username": row["username"],
        "nickname": row["nickname"],
        "role": role,
        "is_admin": role == "admin",
    }


def get_user(user_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM oneid_users WHERE user_id = %s",
            (user_id,),
        ).fetchone()


def ensure_account_active(user_id: str) -> dict[str, Any]:
    row = get_user(user_id)

    if not row:
        raise HTTPException(status_code=401, detail="계정을 찾을 수 없습니다.")

    if row["global_suspended"]:
        raise HTTPException(
            status_code=403,
            detail=row["suspension_reason"] or "계정이 정지되었습니다.",
        )

    return row


def ensure_site_active(user_id: str, client_id: str) -> None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT reason
            FROM oneid_site_suspensions
            WHERE user_id = %s AND client_id = %s
            """,
            (user_id, client_id),
        ).fetchone()

    if row:
        raise HTTPException(
            status_code=403,
            detail=row["reason"] or "이 사이트에서 계정 사용이 정지되었습니다.",
        )


def issue_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "iss": settings.oneid_issuer_url,
            "iat": now,
            "exp": now + timedelta(hours=2),
            "mode": "oneid",
        },
        settings.oneid_jwt_secret,
        algorithm="HS256",
    )


def issue_sso_token(user_id: str, client_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "iss": settings.oneid_issuer_url,
            "aud": "oneid-sites",
            "iat": now,
            "exp": now + timedelta(hours=2),
            "mode": "sso",
            "client_id": client_id,
        },
        settings.oneid_jwt_secret,
        algorithm="HS256",
    )


def user_from_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.oneid_jwt_secret,
            algorithms=["HS256"],
            issuer=settings.oneid_issuer_url,
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail="로그인이 만료되었거나 유효하지 않습니다.",
        ) from exc

    mode = payload.get("mode")
    user_id = payload.get("sub")

    if not user_id or mode not in ("oneid", "sso"):
        raise HTTPException(status_code=401, detail="유효하지 않은 로그인 토큰입니다.")

    row = ensure_account_active(str(user_id))

    if mode == "sso":
        if payload.get("aud") != "oneid-sites":
            raise HTTPException(status_code=401, detail="유효하지 않은 사이트 로그인입니다.")

        client_id = payload.get("client_id")
        if not client_id:
            raise HTTPException(status_code=401, detail="사이트 정보가 없는 로그인입니다.")

        ensure_site_active(str(user_id), str(client_id))

    return public_user(row)


def require_user(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    return user_from_access_token(token)


def require_admin(authorization: str | None) -> dict[str, Any]:
    user = require_user(authorization)

    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 사용할 수 있습니다.")

    return user


def validated_redirect_uri(client_id: str, redirect_uri: str) -> str:
    allowed = settings.client_redirect_uris.get(client_id, [])

    if redirect_uri not in allowed:
        print("OAUTH REDIRECT CHECK FAILED")
        print("CLIENT_ID:", repr(client_id))
        print("REDIRECT_URI:", repr(redirect_uri))
        print("ALLOWED_URIS:", repr(allowed))

        raise HTTPException(
            status_code=400,
            detail="등록되지 않은 사이트 이동 주소입니다.",
        )

    return redirect_uri


def add_query(uri: str, values: dict[str, str]) -> str:
    parts = urlsplit(uri)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(values)

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


# --------------------------------------------------
# Public configuration
# --------------------------------------------------

@router.get("/public-config")
def public_config() -> dict[str, str]:
    return {"auth_mode": "neon"}


# --------------------------------------------------
# Registration
# --------------------------------------------------

@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterInput) -> dict[str, Any]:
    username = validate_username(payload.username)
    normalized = normalize_username(username)
    nickname = payload.nickname.strip()

    if not nickname:
        raise HTTPException(status_code=422, detail="닉네임을 입력해 주세요.")

    user_id = str(uuid.uuid4())

    is_bootstrap_admin = (
        bool(settings.oneid_bootstrap_admin_username)
        and normalized
        == normalize_username(settings.oneid_bootstrap_admin_username)
    )

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT 1 FROM oneid_users
            WHERE username_normalized = %s
            """,
            (normalized,),
        ).fetchone()

        if existing:
            raise HTTPException(status_code=409, detail="이미 사용 중인 사용자명입니다.")

        # The configured bootstrap username is the only way to assign
        # the initial administrator role during registration.
        role = "user"
        if is_bootstrap_admin:
            admin_exists = conn.execute(
                "SELECT 1 FROM oneid_users WHERE role = 'admin' LIMIT 1"
            ).fetchone()
            if not admin_exists:
                role = "admin"

        try:
            row = conn.execute(
                """
                INSERT INTO oneid_users (
                    user_id, username, username_normalized,
                    nickname, password_hash, role
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    user_id,
                    username,
                    normalized,
                    nickname,
                    password_hash.hash(payload.password),
                    role,
                ),
            ).fetchone()
        except Exception as exc:
            # PostgreSQL unique constraints also protect against
            # simultaneous registration attempts.
            if getattr(exc, "sqlstate", None) == "23505":
                raise HTTPException(
                    status_code=409,
                    detail="이미 사용 중인 사용자명입니다.",
                ) from exc
            raise

    return {
        "message": "ONEID 계정이 생성되었습니다. 로그인해 주세요.",
        "user": public_user(row),
        "auth_mode": "neon",
    }


# --------------------------------------------------
# Login
# --------------------------------------------------

@router.post("/auth/login")
def login(payload: LoginInput) -> dict[str, Any]:
    normalized = normalize_username(payload.username)

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM oneid_users
            WHERE username_normalized = %s
            """,
            (normalized,),
        ).fetchone()

    if not row or not password_hash.verify(payload.password, row["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="사용자명 또는 비밀번호가 올바르지 않습니다.",
        )

    if row["global_suspended"]:
        raise HTTPException(
            status_code=403,
            detail=row["suspension_reason"] or "계정이 정지되었습니다.",
        )

    return {
        "access_token": issue_access_token(row["user_id"]),
        "refresh_token": "",
        "token_type": "bearer",
        "expires_in": 7200,
        "user": public_user(row),
        "auth_mode": "neon",
    }


@router.get("/auth/me")
def me(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return require_user(authorization)


# --------------------------------------------------
# OAuth / PKCE
# --------------------------------------------------

@router.post("/oauth/authorize")
def oauth_authorize(
    payload: OAuthAuthorizeInput,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user = require_user(authorization)
    redirect_uri = validated_redirect_uri(payload.client_id, payload.redirect_uri)

    ensure_account_active(user["id"])
    ensure_site_active(user["id"], payload.client_id)

    if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", payload.code_challenge):
        raise HTTPException(status_code=400, detail="PKCE code challenge 형식이 올바르지 않습니다.")

    code = secrets.token_urlsafe(32)
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM oneid_oauth_codes WHERE expires_at <= NOW()"
        )
        conn.execute(
            """
            INSERT INTO oneid_oauth_codes (
                code_hash, user_id, client_id, redirect_uri,
                code_challenge, expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                code_hash,
                user["id"],
                payload.client_id,
                redirect_uri,
                payload.code_challenge,
                expires_at,
            ),
        )

    return {
        "redirect_uri": add_query(
            redirect_uri,
            {"code": code, "state": payload.state},
        )
    }


@router.post("/oauth/token")
def oauth_token(payload: OAuthTokenInput) -> dict[str, Any]:
    redirect_uri = validated_redirect_uri(payload.client_id, payload.redirect_uri)

    if not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", payload.code_verifier):
        raise HTTPException(status_code=400, detail="PKCE verifier 형식이 올바르지 않습니다.")

    expected_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(payload.code_verifier.encode("ascii")).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )

    code_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)

    # Atomic DELETE ... RETURNING makes the authorization code single-use.
    # Invalid challenges do not consume a code.
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT user_id, code_challenge
            FROM oneid_oauth_codes
            WHERE code_hash = %s
              AND client_id = %s
              AND redirect_uri = %s
              AND expires_at > %s
            FOR UPDATE
            """,
            (code_hash, payload.client_id, redirect_uri, now),
        ).fetchone()

        if not row or not secrets.compare_digest(
            row["code_challenge"], expected_challenge
        ):
            raise HTTPException(
                status_code=400,
                detail="로그인 코드가 만료되었거나 유효하지 않습니다.",
            )

        conn.execute(
            "DELETE FROM oneid_oauth_codes WHERE code_hash = %s",
            (code_hash,),
        )

    user_row = ensure_account_active(row["user_id"])
    ensure_site_active(row["user_id"], payload.client_id)

    token = issue_sso_token(row["user_id"], payload.client_id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 7200,
        "user": public_user(user_row),
    }


# --------------------------------------------------
# Admin: user list and roles
# --------------------------------------------------

@router.get("/admin/users")
def admin_users(
    authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    require_admin(authorization)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id, username, nickname, role,
                   global_suspended, suspension_reason,
                   created_at, updated_at
            FROM oneid_users
            ORDER BY created_at DESC
            """
        ).fetchall()

        suspensions = conn.execute(
            """
            SELECT user_id, client_id, reason, created_at
            FROM oneid_site_suspensions
            ORDER BY created_at DESC
            """
        ).fetchall()

    sites_by_user: dict[str, list[dict[str, Any]]] = {}
    for suspension in suspensions:
        sites_by_user.setdefault(suspension["user_id"], []).append(
            {
                "client_id": suspension["client_id"],
                "reason": suspension["reason"],
                "created_at": suspension["created_at"],
            }
        )

    result = []
    for row in rows:
        item = public_user(row)
        item.update(
            {
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "global_suspended": row["global_suspended"],
                "suspension_reason": row["suspension_reason"],
                "site_suspensions": sites_by_user.get(row["user_id"], []),
            }
        )
        result.append(item)

    return result


@router.patch("/admin/users/{user_id}/role")
def set_user_role(
    user_id: str,
    payload: RoleInput,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = require_admin(authorization)

    if user_id == admin["id"]:
        raise HTTPException(
            status_code=409,
            detail="현재 로그인한 관리자의 권한은 여기서 변경할 수 없습니다.",
        )

    with get_connection() as conn:
        target = conn.execute(
            "SELECT user_id, role FROM oneid_users WHERE user_id = %s FOR UPDATE",
            (user_id,),
        ).fetchone()

        if not target:
            raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")

        if target["role"] == "admin" and payload.role == "user":
            admin_count = conn.execute(
                "SELECT COUNT(*) AS count FROM oneid_users WHERE role = 'admin'"
            ).fetchone()["count"]

            if admin_count <= 1:
                raise HTTPException(
                    status_code=409,
                    detail="마지막 관리자의 권한은 해제할 수 없습니다.",
                )

        conn.execute(
            """
            UPDATE oneid_users
            SET role = %s, updated_at = NOW()
            WHERE user_id = %s
            """,
            (payload.role, user_id),
        )

    return {
        "id": user_id,
        "role": payload.role,
        "is_admin": payload.role == "admin",
    }


# --------------------------------------------------
# Admin: global suspension
# --------------------------------------------------

@router.patch("/admin/users/{user_id}/suspension")
def set_global_suspension(
    user_id: str,
    payload: GlobalSuspensionInput,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = require_admin(authorization)

    if user_id == admin["id"] and payload.suspended:
        raise HTTPException(
            status_code=409,
            detail="현재 로그인한 관리자 계정은 여기서 정지할 수 없습니다.",
        )

    with get_connection() as conn:
        row = conn.execute(
            "SELECT user_id FROM oneid_users WHERE user_id = %s",
            (user_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")

        conn.execute(
            """
            UPDATE oneid_users
            SET global_suspended = %s,
                suspension_reason = %s,
                updated_at = NOW()
            WHERE user_id = %s
            """,
            (
                payload.suspended,
                payload.reason if payload.suspended else None,
                user_id,
            ),
        )

    return {
        "id": user_id,
        "global_suspended": payload.suspended,
        "reason": payload.reason if payload.suspended else None,
    }


# --------------------------------------------------
# Admin: per-site suspension
# --------------------------------------------------

@router.patch("/admin/users/{user_id}/site-suspensions/{client_id}")
def set_site_suspension(
    user_id: str,
    client_id: str,
    payload: SiteSuspensionInput,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)

    if client_id not in settings.client_redirect_uris:
        raise HTTPException(status_code=404, detail="등록되지 않은 사이트입니다.")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT user_id FROM oneid_users WHERE user_id = %s",
            (user_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")

        if payload.suspended:
            conn.execute(
                """
                INSERT INTO oneid_site_suspensions (user_id, client_id, reason)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, client_id)
                DO UPDATE SET reason = EXCLUDED.reason,
                              created_at = NOW()
                """,
                (user_id, client_id, payload.reason),
            )
        else:
            conn.execute(
                """
                DELETE FROM oneid_site_suspensions
                WHERE user_id = %s AND client_id = %s
                """,
                (user_id, client_id),
            )

    return {
        "id": user_id,
        "client_id": client_id,
        "suspended": payload.suspended,
        "reason": payload.reason if payload.suspended else None,
    }


@router.get("/admin/sites")
def admin_sites(
    authorization: str | None = Header(default=None),
) -> list[str]:
    require_admin(authorization)
    return list(settings.client_redirect_uris.keys())


@router.delete("/admin/users/{user_id}")
def delete_user(
    user_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    admin = require_admin(authorization)
    if user_id == admin["id"]:
        raise HTTPException(
            status_code=409,
            detail="현재 로그인한 관리자 계정은 삭제할 수 없습니다.",
        )
    with get_connection() as conn:
        target = conn.execute(
            "SELECT user_id, role FROM oneid_users WHERE user_id = %s FOR UPDATE",
            (user_id,),
        ).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
        if target["role"] == "admin":
            admin_count = conn.execute(
                "SELECT COUNT(*) AS count FROM oneid_users WHERE role = 'admin'"
            ).fetchone()["count"]
            if admin_count <= 1:
                raise HTTPException(
                    status_code=409,
                    detail="마지막 관리자 계정은 삭제할 수 없습니다.",
                )
        conn.execute("DELETE FROM oneid_site_suspensions WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM oneid_oauth_codes WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM oneid_users WHERE user_id = %s", (user_id,))
    return {"id": user_id, "deleted": True}