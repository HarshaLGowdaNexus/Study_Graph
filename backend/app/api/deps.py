"""
Authentication and security dependencies for StudyGraph.
Relies on Decision D13: Supabase Auth.
Enforces Rule 11: Privacy rule - each user's data stays private to that user.
"""

from typing import Optional, Dict, Any
import httpx
from fastapi import Header, HTTPException, status
from pydantic import BaseModel
from backend.app.core.config import settings
from backend.app.database import get_db_cursor


class CurrentUser(BaseModel):
    id: str
    email: str
    name: Optional[str] = None


def ensure_user_in_db(user_id: str, email: str, name: Optional[str] = None) -> None:
    """
    Ensures the authenticated Supabase user exists in our relational 'users' table.
    Uses ON CONFLICT to cleanly handle existing students.
    Catches transient connection errors in local development or offline modes.
    """
    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (id, email, name)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE 
                SET email = EXCLUDED.email,
                    name = COALESCE(EXCLUDED.name, users.name);
                """,
                (user_id, email, name or email.split("@")[0]),
            )
    except Exception as e:
        logger.warning(f"Could not ensure user in DB (safe fallback): {e}")


async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_test_user_id: Optional[str] = Header(None),
    x_test_user_email: Optional[str] = Header(None),
) -> CurrentUser:
    """
    Validates the student's authentication token and returns the current user.
    Calls Supabase Auth API to verify JWT bearer tokens securely.
    Supports test headers in testing/development environments.
    """
    # 1. Test environment bypass for automated tests and local development
    if settings.APP_ENV in ("development", "testing"):
        if x_test_user_id:
            test_email = x_test_user_email or f"user_{x_test_user_id[:8]}@example.com"
            return CurrentUser(id=x_test_user_id, email=test_email, name="Test Student")
        # In local development, if no auth token is provided, safely fall back to default demo student
        if not authorization or not authorization.startswith("Bearer "):
            default_user_id = "11111111-1111-4111-8111-111111111111"
            default_email = "alex@university.edu"
            return CurrentUser(id=default_user_id, email=default_email, name="Alex Chen (Student A)")

    # 2. Check Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in to access your study notes.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Verify token with Supabase Auth endpoint
    auth_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": settings.SUPABASE_ANON_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(auth_url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Your session has expired or is invalid. Please sign in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            data = resp.json()
            user_id = data.get("id")
            email = data.get("email", "")
            user_meta = data.get("user_metadata", {})
            name = user_meta.get("full_name") or user_meta.get("name")

            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User identification missing from authentication token.",
                )

            # Sync user record to PostgreSQL users table
            ensure_user_in_db(user_id, email, name)

            return CurrentUser(id=user_id, email=email, name=name)

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to reach authentication service: {str(e)}",
        )

