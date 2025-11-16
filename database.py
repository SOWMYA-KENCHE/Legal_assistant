import sqlite3
import hashlib
from typing import List, Dict, Any, Optional, Tuple

def hash_password(password: str) -> str:
    """Hashes the password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()
def db_init() -> None:
    """Initializes the database and creates/alters tables as needed."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Create chat_history table
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    c.execute("""
        CREATE TABLE IF NOT EXISTS precedents1 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT,
            court TEXT,
            year TEXT,
            url TEXT,
            confidence REAL,
            ai_summary TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    

    # --- Migration: Add columns if they don't exist ---
    
    def add_column(table: str, column: str, col_type: str) -> None:
        """Helper function to add a column if it doesn't exist."""
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise
    
    # Add columns to users table
    add_column("users", "current_summary_text", "TEXT")
    add_column("users", "current_pdf_name", "TEXT")
    # Add columns to chat_history table
    add_column("chat_history", "sender", "TEXT")
    add_column("chat_history", "message", "TEXT")
    add_column("chat_history", "source", "TEXT")
    add_column("precedents1", "ai_summary", "TEXT")

    # --- END OF MIGRATION ---
    conn.commit()
    conn.close()
    print("Database initialized successfully.")
    
def db_init():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    # USERS table already exists...

    # # 🆕 DOCUMENTS table
    # c.execute("""
    #     CREATE TABLE IF NOT EXISTS documents (
    #         id INTEGER PRIMARY KEY AUTOINCREMENT,
    #         user_id INTEGER NOT NULL,
    #         pdf_name TEXT NOT NULL,
    #         summary TEXT,
    #         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    #         FOREIGN KEY (user_id) REFERENCES users(id)
    #     )
    # """)

    # Precedents table — now linked to document_id
    c.execute("""
        CREATE TABLE IF NOT EXISTS precedents1 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            document_id INTEGER,
            name TEXT,
            court TEXT,
            year TEXT,
            url TEXT,
            confidence REAL,
            ai_summary TEXT,
            raw_json TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (document_id) REFERENCES documents(id)
            
        )
    """)

     # Try to add new column if old DB exists
    try:
        c.execute("ALTER TABLE precedents1 ADD COLUMN raw_json TEXT")
    except sqlite3.OperationalError:
        pass  # already exists

    conn.commit()
    conn.close()
    print("Database initialized successfully.1")

import sqlite3

def save_fact_check_results(user_id: int, fact_results: list[dict]) -> None:
    """Save fact-checking results into the database."""
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    for item in fact_results:
        if "statement" not in item:
            continue
        c.execute('''
            INSERT INTO fact_check_history (user_id, statement, supported, confidence, evidence)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            item.get("statement", ""),
            int(item.get("supported", False)),  # store as 0/1
            float(item.get("confidence", 0.0)),
            item.get("evidence", "")
        ))
    conn.commit()
    conn.close()
    print(f"[DB] ✅ Saved {len(fact_results)} fact check results for user {user_id}")

def load_fact_check_history(user_id: int) -> list[dict]:
    """Retrieve all fact-check history for a user."""
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('''
        SELECT statement, supported, confidence, evidence, timestamp
        FROM fact_check_history
        WHERE user_id=?
        ORDER BY timestamp DESC
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()

    return [
        {
            "statement": row[0],
            "supported": bool(row[1]),
            "confidence": row[2],
            "evidence": row[3],
            "timestamp": row[4]
        }
        for row in rows
    ]


if __name__ == '__main__':
    db_init()

