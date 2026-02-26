#!/usr/bin/env python3
import argparse
import requests
import sqlite3
import json
import sys
from datetime import datetime

API_BASE = "http://127.0.0.1:8000"
DB_PATH = "avara_state.db"

def _print_error(msg):
    print(f"\033[91m[ERROR]\033[0m {msg}")
    
def _print_success(msg):
    print(f"\033[92m[SUCCESS]\033[0m {msg}")

def request_provision(args):
    payload = {
        "role_name": args.role,
        "description": args.desc,
        "scopes": args.scopes,
        "ttl_seconds": args.ttl
    }
    try:
        resp = requests.post(f"{API_BASE}/iam/provision", json=payload)
        resp.raise_for_status()
        data = resp.json()
        _print_success(f"Provisioned ID: {data['agent_id']} (TTL: {data['ttl']}s)")
    except Exception as e:
        _print_error(f"Provisioning failed: {e}")

def request_revoke(args):
    try:
        resp = requests.delete(f"{API_BASE}/iam/revoke/{args.agent_id}")
        resp.raise_for_status()
        _print_success(f"Revoked Identity: {args.agent_id}")
    except Exception as e:
        _print_error(f"Revocation failed: {e}")

def resolve_approval(action_id, decision):
    endpoint = f"{API_BASE}/guard/approvals/{action_id}/{decision}"
    try:
        resp = requests.post(endpoint)
        resp.raise_for_status()
        _print_success(f"Action {action_id} {decision}d successfully.")
    except requests.exceptions.HTTPError as e:
        _print_error(f"Failed: {e.response.text}")
    except Exception as e:
        _print_error(f"Error: {e}")

def list_pending(args):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("SELECT action_id, agent_id, action_type, target, timestamp FROM approvals WHERE status = 'PENDING'")
            rows = cursor.fetchall()
            
            if not rows:
                print("No pending approvals.")
                return
                
            print("\n--- PENDING CIRCUIT BREAKER APPROVALS ---")
            for r in rows:
                dt = datetime.fromtimestamp(r[4]).strftime('%Y-%m-%d %H:%M:%S')
                print(f"ID:     {r[0]}")
                print(f"Agent:  {r[1]}")
                print(f"Action: {r[2]} -> {r[3]}")
                print(f"Time:   {dt}")
                print("-" * 40)
    except Exception as e:
        _print_error(f"Could not read DB: {e}")

def main():
    parser = argparse.ArgumentParser(description="AVARA Security Control CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Provision
    p_prov = subparsers.add_parser("provision", help="Provision a new agent identity")
    p_prov.add_argument("role", type=str, help="Name of role (e.g., prod_agent)")
    p_prov.add_argument("desc", type=str, help="Description")
    p_prov.add_argument("--scopes", nargs="+", default=["*"], help="List of allowed tool scopes (e.g., execute:read_file)")
    p_prov.add_argument("--ttl", type=int, default=3600, help="Time to live in seconds")
    p_prov.set_defaults(func=request_provision)

    # Revoke
    p_rev = subparsers.add_parser("revoke", help="Revoke an active agent identity")
    p_rev.add_argument("agent_id", type=str, help="The Agent ID to revoke")
    p_rev.set_defaults(func=request_revoke)

    # Pending
    p_pend = subparsers.add_parser("pending", help="List high-risk actions awaiting approval")
    p_pend.set_defaults(func=list_pending)

    # Approve
    p_app = subparsers.add_parser("approve", help="Approve a pending action")
    p_app.add_argument("action_id", type=str, help="The Action ID to approve")
    p_app.set_defaults(func=lambda args: resolve_approval(args.action_id, "approve"))

    # Deny
    p_deny = subparsers.add_parser("deny", help="Deny a pending action")
    p_deny.add_argument("action_id", type=str, help="The Action ID to deny")
    p_deny.set_defaults(func=lambda args: resolve_approval(args.action_id, "deny"))

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
