"""
Authentication and authorization module for Fainzy Simulator API
"""

import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel, EmailStr
import psycopg2
from psycopg2.extras import DictCursor
import os
import logging

logger = logging.getLogger(__name__)

# JWT Configuration
SIM_ENV = os.getenv("SIM_ENV", "development").strip().lower()
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip()
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7

ALLOWED_ROLES = {"admin", "user", "operator", "runner", "viewer"}
MUTATING_ROLES = {"admin", "user", "operator", "runner"}
DELETING_ROLES = {"admin", "user", "operator"}

if SIM_ENV in {"production", "prod"} and not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is required when SIM_ENV=production.")

if SIM_ENV in {"production", "prod"} and JWT_SECRET_KEY in {
    "your-secret-key-change-in-production",
    "dev-only-change-me",
}:
    raise RuntimeError("JWT_SECRET_KEY must be changed before production use.")

# Pydantic models for authentication
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    role: str
    created_at: datetime
    last_login: Optional[datetime] = None
    preferences: Dict[str, Any] = {}


class AuthManager:
    def __init__(self, db_connection_string: str):
        self.db_connection_string = db_connection_string
    
    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(self.db_connection_string)
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt
    
    def create_refresh_token(self, user_id: int):
        """Create refresh token and store in database"""
        expires_at = datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_token = self.create_access_token(
            {"sub": str(user_id), "type": "refresh"},
            expires_delta=timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        )
        
        # Store refresh token in database
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO user_sessions (user_id, refresh_token, expires_at)
                        VALUES (%s, %s, %s)
                        """,
                        (user_id, refresh_token, expires_at)
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Failed to store refresh token: {e}")
            raise
        
        return refresh_token
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.PyJWTError as e:
            logger.warning(f"Invalid token: {e}")
            return None
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute(
                        """
                        SELECT id, username, email, password_hash, role, 
                               created_at, last_login, preferences, is_active
                        FROM users 
                        WHERE username = %s AND is_active = TRUE
                        """,
                        (username,)
                    )
                    user = cursor.fetchone()
                    return dict(user) if user else None
        except Exception as e:
            logger.error(f"Failed to get user by username: {e}")
            return None
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute(
                        """
                        SELECT id, username, email, role, created_at, 
                               last_login, preferences, is_active
                        FROM users 
                        WHERE id = %s AND is_active = TRUE
                        """,
                        (user_id,)
                    )
                    user = cursor.fetchone()
                    return dict(user) if user else None
        except Exception as e:
            logger.error(f"Failed to get user by ID: {e}")
            return None
    
    def create_user(self, user_data: UserCreate) -> Dict[str, Any]:
        """Create new user"""
        # Check if user already exists
        if self.get_user_by_username(user_data.username):
            raise ValueError("Username already exists")
        
        # Hash password
        password_hash = self.hash_password(user_data.password)
        
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO users (username, email, password_hash, role)
                        VALUES (%s, %s, %s, 'user')
                        RETURNING id, username, email, role, created_at
                        """,
                        (user_data.username, user_data.email, password_hash)
                    )
                    user = cursor.fetchone()
                    conn.commit()
                    
                    return {
                        "id": user[0],
                        "username": user[1],
                        "email": user[2],
                        "role": user[3],
                        "created_at": user[4]
                    }
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user with username and password"""
        user = self.get_user_by_username(username)
        if not user:
            return None
        
        if not self.verify_password(password, user['password_hash']):
            return None
        
        # Update last login
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE users SET last_login = NOW() WHERE id = %s",
                        (user['id'],)
                    )
                    conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update last login: {e}")
        
        # Remove password hash from response
        user.pop('password_hash', None)
        return user
    
    def refresh_access_token(self, refresh_token: str) -> Optional[TokenResponse]:
        """Refresh access token using refresh token"""
        # Verify refresh token
        payload = self.verify_token(refresh_token)
        if not payload or payload.get('type') != 'refresh':
            return None
        
        user_id = int(payload.get('sub'))
        if not user_id:
            return None
        
        # Check if refresh token exists and is valid
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT us.user_id, us.expires_at
                        FROM user_sessions us
                        WHERE us.refresh_token = %s AND us.expires_at > NOW()
                        """,
                        (refresh_token,)
                    )
                    session = cursor.fetchone()
                    
                    if not session or session[0] != user_id:
                        return None
                    
                    # Update last used timestamp
                    cursor.execute(
                        "UPDATE user_sessions SET last_used_at = NOW() WHERE refresh_token = %s",
                        (refresh_token,)
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Failed to validate refresh token: {e}")
            return None
        
        # Get user
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        
        # Create new access token
        access_token = self.create_access_token({"sub": str(user_id), "username": user['username']})
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    
    def logout(self, refresh_token: str) -> bool:
        """Logout user by removing refresh token"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM user_sessions WHERE refresh_token = %s",
                        (refresh_token,)
                    )
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Failed to logout: {e}")
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM user_sessions WHERE expires_at < NOW()"
                    )
                    deleted_count = cursor.rowcount
                    conn.commit()
                    return deleted_count
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0
    
    def list_users(self) -> list[dict]:
        """List all users (admin only)"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute("""
                        SELECT id, username, email, role, is_active, created_at, last_login
                        FROM users 
                        ORDER BY created_at DESC
                    """)
                    return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            return []

    def update_user(self, user_id: int, user_data: dict) -> dict:
        """Update user information (admin only)"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    # Build dynamic update query
                    update_fields = []
                    values = []
                    
                    for field in ['username', 'email', 'role', 'is_active']:
                        if field not in user_data:
                            continue

                        if field == "role":
                            role = str(user_data[field]).strip().lower()
                            if role not in ALLOWED_ROLES:
                                raise ValueError(f"Unsupported role: {role}")
                            user_data[field] = role

                        update_fields.append(f"{field} = %s")
                        values.append(user_data[field])
                    
                    if not update_fields:
                        raise ValueError("No valid fields to update")
                    
                    values.append(user_id)
                    query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s RETURNING id, username, email, role, is_active, created_at, last_login"
                    
                    cursor.execute(query, values)
                    conn.commit()
                    
                    result = cursor.fetchone()
                    if not result:
                        raise ValueError("User not found")
                        
                    return dict(result)
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            raise ValueError(f"Failed to update user: {e}")

    def delete_user(self, user_id: int) -> bool:
        """Delete user (admin only)"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Delete user sessions first
                    cursor.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
                    # Delete user
                    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete user: {e}")
            return False

    def reset_password(self, user_id: int, new_password: str) -> bool:
        """Reset user password (admin only)"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Hash new password
                    password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    
                    # Update password and invalidate all sessions
                    cursor.execute(
                        "UPDATE users SET password_hash = %s WHERE id = %s",
                        (password_hash, user_id)
                    )
                    cursor.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to reset password: {e}")
            return False


# Global auth manager instance
auth_manager: Optional[AuthManager] = None


def init_auth(db_connection_string: str):
    """Initialize authentication manager"""
    global auth_manager
    auth_manager = AuthManager(db_connection_string)


def get_auth_manager() -> AuthManager:
    """Get authentication manager instance"""
    if auth_manager is None:
        raise RuntimeError("Auth manager not initialized")
    return auth_manager
