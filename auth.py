import re
import sqlite3
from passlib.context import CryptContext
from typing import List, Dict, Any, Optional, Tuple
# Password hashing setup
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
# VALIDATION FUNCTIONS

import sqlite3

def get_username_by_id(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def is_valid_email(email: str) -> bool:
    """
    Validates if the username is a proper Gmail address (must end exactly with @gmail.com).
    """
    return bool(re.match(r"^[A-Za-z0-9._%+-]+@gmail\.com$", email.strip(), re.IGNORECASE))

def is_strong_password(password: str) -> Tuple[bool, str]:
    """Checks password strength based on defined rules."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character."
    return True, "Valid password."
# AUTH CORE FUNCTIONS
def hash_password(password: str) -> str:
    """Hashes the password securely."""
    return pwd_context.hash(password)

def check_password(password: str, hashed_password: str) -> bool:
    """Verifies the entered password against stored hash."""
    try:
        return pwd_context.verify(password, hashed_password)
    except Exception:
        return False

def add_user(username: str, password: str) -> Tuple[bool, str]:
    """
    Adds a new user to the database.
    Returns (success, message) tuple.
    """
    # --- VALIDATION LAYER ---
    if not is_valid_email(username):
        return False, "Invalid email format. Please use a valid email address."
    
    strong, msg = is_strong_password(password)
    if not strong:
        return False, msg

    hashed = hash_password(password)
    sql = "INSERT INTO users (username, password_hash) VALUES (?, ?)"
    
    try:
        with sqlite3.connect('users.db') as conn:
            c = conn.cursor()
            c.execute(sql, (username, hashed))
        return True, "User created successfully!"
    except sqlite3.IntegrityError:
        return False, "This email is already registered."
    except Exception as e:
        print(f"Error adding user: {e}")
        return False, "Internal server error. Please try again later."

def check_user(username: str, password: str) -> Optional[int]:
    """Checks credentials and returns user_id if valid."""
    sql = "SELECT id, password_hash FROM users WHERE username = ?"
    try:
        with sqlite3.connect('users.db') as conn:
            c = conn.cursor()
            c.execute(sql, (username,))
            user_data = c.fetchone()
        if user_data:
            user_id, stored_hash = user_data
            if check_password(password, stored_hash):
                return user_id
        return None
    except Exception as e:
        print(f"Error checking user: {e}")
        return None
# CHAT & SUMMARY FUNCTIONS

def save_chat_message(user_id: int, sender: str, message: str, source: Optional[str] = None) -> None:
    sql = "INSERT INTO chat_history (user_id, sender, message, source) VALUES (?, ?, ?, ?)"
    try:
        with sqlite3.connect('users.db') as conn:
            conn.execute(sql, (user_id, sender, message, source))
    except Exception as e:
        print(f"Error saving chat message: {e}")

def load_chat_history(user_id: int) -> List[Dict[str, Any]]:
    sql = "SELECT sender, message, source FROM chat_history WHERE user_id = ? ORDER BY timestamp ASC"
    display_messages = []
    try:
        with sqlite3.connect('users.db') as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(sql, (user_id,))
            history_data = c.fetchall()
        for row in history_data:
            role = "user" if row["sender"] == "user" else "assistant"
            msg = {"role": role, "content": row["message"]}
            if row["source"]:
                msg["source"] = row["source"]
            display_messages.append(msg)
    except Exception as e:
        print(f"Error loading chat history: {e}")
    return display_messages


def save_document_summary(user_id: int, summary_text: Optional[str], pdf_name: Optional[str]) -> None:
    sql = "UPDATE users SET current_summary_text = ?, current_pdf_name = ? WHERE id = ?"
    try:
        with sqlite3.connect('users.db') as conn:
            conn.execute(sql, (summary_text, pdf_name, user_id))
    except Exception as e:
        print(f"Error saving document summary: {e}")

def load_document_summary(user_id: int) -> Tuple[Optional[str], Optional[str]]:
    sql = "SELECT current_summary_text, current_pdf_name FROM users WHERE id = ?"
    try:
        with sqlite3.connect('users.db') as conn:
            c = conn.cursor()
            c.execute(sql, (user_id,))
            data = c.fetchone()
        if data:
            return data[0], data[1]
    except Exception as e:
        print(f"Error loading document summary: {e}")
    return None, None

