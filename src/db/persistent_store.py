import sqlite3
import json
from typing import Dict, Any, List, Optional
import time

DATABASE_PATH = "./avara_state.db"

class PersistentStore:
    """
    Executes Database Persistence rules:
    - Maintains Agent Identity State across reboots
    - Stores Tool Registries persistently
    - Replaces in-memory representations for production
    """
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Agent IAM Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    role_name TEXT,
                    scopes TEXT, 
                    created_at REAL,
                    ttl_seconds INTEGER
                )
            ''')
            
            # Tools Registry Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tools (
                    name TEXT PRIMARY KEY,
                    description TEXT,
                    parameters_schema TEXT,
                    required_permissions TEXT,
                    is_active BOOLEAN
                )
            ''')
            
            # Behavioral Anomaly History
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    action_type TEXT,
                    target TEXT,
                    timestamp REAL
                )
            ''')
            
            # Pending Approvals
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS approvals (
                    action_id TEXT PRIMARY KEY,
                    agent_id TEXT,
                    action_type TEXT,
                    target TEXT,
                    parameters TEXT,
                    status TEXT,
                    timestamp REAL
                )
            ''')
            conn.commit()

    # --- IAM Persistence ---
    def save_agent(self, agent_id: str, role_name: str, scopes: List[str], ttl: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agents (agent_id, role_name, scopes, created_at, ttl_seconds) VALUES (?, ?, ?, ?, ?)",
                (agent_id, role_name, json.dumps(scopes), time.time(), ttl)
            )

    def load_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT role_name, scopes, created_at, ttl_seconds FROM agents WHERE agent_id = ?", (agent_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "role_name": row[0],
                    "scopes": json.loads(row[1]),
                    "created_at": row[2],
                    "ttl_seconds": row[3]
                }
        return None

    def delete_agent(self, agent_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))

    # --- Tool Persistence ---
    def save_tool(self, name: str, desc: str, schema: dict, perms: list):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tools (name, description, parameters_schema, required_permissions, is_active) VALUES (?, ?, ?, ?, ?)",
                (name, desc, json.dumps(schema), json.dumps(perms), True)
            )

    def load_tool(self, name: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT description, parameters_schema, required_permissions, is_active FROM tools WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return {
                    "description": row[0],
                    "parameters_schema": json.loads(row[1]),
                    "required_permissions": json.loads(row[2]),
                    "is_active": bool(row[3])
                }
        return None

    # --- Anomaly Execution Persistence ---
    def log_execution(self, agent_id: str, action: str, target: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO executions (agent_id, action_type, target, timestamp) VALUES (?, ?, ?, ?)",
                (agent_id, action, target, time.time())
            )

    def get_recent_executions(self, agent_id: str, seconds_ago: float) -> List[Dict[str, Any]]:
        threshold = time.time() - seconds_ago
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT action_type, target, timestamp FROM executions WHERE agent_id = ? AND timestamp > ?",
                (agent_id, threshold)
            )
            return [{"action": row[0], "target": row[1], "timestamp": row[2]} for row in cursor.fetchall()]

    # --- Approvals Persistence ---
    def save_approval(self, action_id: str, agent_id: str, action_type: str, target: str, parameters: dict, status: str = "PENDING"):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO approvals (action_id, agent_id, action_type, target, parameters, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (action_id, agent_id, action_type, target, json.dumps(parameters), status, time.time())
            )

    def get_approval(self, action_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT agent_id, action_type, target, parameters, status, timestamp FROM approvals WHERE action_id = ?", (action_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "action_id": action_id,
                    "agent_id": row[0],
                    "action_type": row[1],
                    "target": row[2],
                    "parameters": json.loads(row[3]),
                    "status": row[4],
                    "timestamp": row[5]
                }
        return None

    def update_approval_status(self, action_id: str, new_status: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE approvals SET status = ?, timestamp = ? WHERE action_id = ?", (new_status, time.time(), action_id))

