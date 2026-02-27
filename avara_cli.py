#!/usr/bin/env python3
"""
AVARA CLI — Runtime Authority Control Interface
Interactive + Direct command modes for managing the AVARA security system.
"""
import argparse
import requests
import sqlite3
import sys
import os
import glob
import shlex
from datetime import datetime

API_BASE = "http://127.0.0.1:8000"
DB_PATH = "avara_state.db"
LOG_DIR = "./logs"
VERSION = "1.0.0"

# ─── ANSI Colors ─────────────────────────────────────────────────────────────
ORANGE = "\033[38;5;208m"
YELLOW = "\033[38;5;220m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
RED    = "\033[91m"
GRAY   = "\033[90m"
WHITE  = "\033[97m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

# ─── ASCII Logo ───────────────────────────────────────────────────────────────
LOGO = rf"""{ORANGE}{BOLD}
  /$$$$$$  /$$    /$$  /$$$$$$  /$$$$$$$   /$$$$$$
 /$$__  $$| $$   | $$ /$$__  $$| $$__  $$ /$$__  $$
| $$  \ $$| $$   | $$| $$  \ $$| $$  \ $$| $$  \ $$
| $$$$$$$$|  $$ / $$/| $$$$$$$$| $$$$$$$/| $$$$$$$$
| $$__  $$ \  $$ $$/ | $$__  $$| $$__  $$| $$__  $$
| $$  | $$  \  $$$/  | $$  | $$| $$  \ $$| $$  | $$
| $$  | $$   \  $/   | $$  | $$| $$  | $$| $$  | $$
|__/  |__/    \_/    |__/  |__/|__/  |__/|__/  |__/
{RESET}"""

TAGLINE = f"{GRAY}  Autonomous Validation & Agent Risk Authority  ·  v{VERSION}{RESET}"
DIVIDER = f"{GRAY}{'─' * 62}{RESET}"
PROMPT  = f"{ORANGE}{BOLD}avara>{RESET} "

# ─── Output Helpers ───────────────────────────────────────────────────────────
def ok(msg):   print(f"  {GREEN}✔{RESET}  {msg}")
def err(msg):  print(f"  {RED}✖{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def info(msg): print(f"  {CYAN}ℹ{RESET}  {msg}")

def print_banner():
    print(LOGO)
    print(TAGLINE)
    print()

def print_help():
    print_banner()
    print(DIVIDER)
    print(f"\n{CYAN}{BOLD}  IDENTITY MANAGEMENT{RESET}")
    _cmd("provision", "<role> <desc> [--scopes ...] [--ttl N]", "Provision a new ephemeral agent identity")
    _cmd("revoke",    "<agent_id>",                             "Revoke an active agent identity")
    _cmd("agents",    "",                                       "List all active agent identities")

    print(f"\n{CYAN}{BOLD}  CIRCUIT BREAKER{RESET}")
    _cmd("pending",   "",             "List high-risk actions awaiting approval")
    _cmd("approve",   "<action_id>",  "Approve a halted action")
    _cmd("deny",      "<action_id>",  "Deny a halted action")

    print(f"\n{CYAN}{BOLD}  MONITORING{RESET}")
    _cmd("status",    "",             "Check AVARA API server health")
    _cmd("logs",      "[--tail N]",   "View recent audit log entries")

    print(f"\n{CYAN}{BOLD}  GENERAL{RESET}")
    _cmd("help",      "",             "Show this help screen")
    _cmd("clear",     "",             "Clear the terminal")
    _cmd("exit",      "",             "Exit the AVARA shell")

    print(f"\n{DIVIDER}")
    print(f"  {DIM}Server: {API_BASE}  ·  DB: {DB_PATH}  ·  Logs: {LOG_DIR}{RESET}\n")

def _cmd(name, args, desc):
    print(f"    {ORANGE}{BOLD}{name:<12}{RESET} {WHITE}{args:<36}{RESET} {DIM}{desc}{RESET}")

# ─── Command Handlers ─────────────────────────────────────────────────────────
def cmd_provision(args):
    payload = {
        "role_name":   args.role,
        "description": args.desc,
        "scopes":      args.scopes,
        "ttl_seconds": args.ttl
    }
    try:
        r = requests.post(f"{API_BASE}/iam/provision", json=payload, timeout=5)
        r.raise_for_status()
        d = r.json()
        ok("Identity provisioned")
        print(f"    {GRAY}Agent ID :{RESET} {WHITE}{d['agent_id']}{RESET}")
        print(f"    {GRAY}Role     :{RESET} {WHITE}{args.role}{RESET}")
        print(f"    {GRAY}Scopes   :{RESET} {WHITE}{', '.join(d['scopes'])}{RESET}")
        print(f"    {GRAY}TTL      :{RESET} {WHITE}{d['ttl']}s{RESET}")
    except requests.exceptions.ConnectionError:
        err("Cannot reach AVARA server. Is it running?")
    except Exception as e:
        err(f"Provisioning failed: {e}")

def cmd_revoke(args):
    try:
        r = requests.delete(f"{API_BASE}/iam/revoke/{args.agent_id}", timeout=5)
        r.raise_for_status()
        ok(f"Identity {ORANGE}{args.agent_id}{RESET} revoked.")
    except requests.exceptions.ConnectionError:
        err("Cannot reach AVARA server. Is it running?")
    except Exception as e:
        err(f"Revocation failed: {e}")

def cmd_agents(args):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT agent_id, role_name, scopes, created_at, ttl_seconds FROM agents"
            ).fetchall()
        if not rows:
            info("No active agent identities.")
            return

        import json
        print(f"\n  {CYAN}{BOLD}ACTIVE AGENT IDENTITIES{RESET}  ({len(rows)})\n")
        for r in rows:
            created = datetime.fromtimestamp(r[3]).strftime('%Y-%m-%d %H:%M:%S')
            scopes = json.loads(r[2])
            expired = (datetime.now().timestamp() - r[3]) > r[4]
            status_badge = f"{RED}EXPIRED{RESET}" if expired else f"{GREEN}ACTIVE{RESET}"
            print(f"  {GRAY}{'─'*56}{RESET}")
            print(f"    {CYAN}ID{RESET}      {r[0]}  [{status_badge}]")
            print(f"    {GRAY}Role  :{RESET}  {r[1]}")
            print(f"    {GRAY}Scopes:{RESET}  {', '.join(scopes)}")
            print(f"    {GRAY}Since :{RESET}  {created}  {DIM}(TTL: {r[4]}s){RESET}")
        print()
    except Exception as e:
        err(f"Could not read DB: {e}")

def cmd_pending(args):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT action_id, agent_id, action_type, target, timestamp "
                "FROM approvals WHERE status = 'PENDING'"
            ).fetchall()

        if not rows:
            info("No pending approvals. All clear.")
            return

        print(f"\n  {RED}{BOLD}PENDING CIRCUIT BREAKER APPROVALS{RESET}  ({len(rows)})\n")
        for r in rows:
            dt = datetime.fromtimestamp(r[4]).strftime('%Y-%m-%d %H:%M:%S')
            print(f"  {GRAY}{'─'*56}{RESET}")
            print(f"    {CYAN}Action ID{RESET}  {r[0]}")
            print(f"    {GRAY}Agent   :{RESET}  {r[1]}")
            print(f"    {GRAY}Action  :{RESET}  {RED}{BOLD}{r[2]}{RESET}  →  {r[3]}")
            print(f"    {GRAY}Halted  :{RESET}  {dt}")
            print(f"    {GRAY}Resolve :{RESET}  {DIM}approve {r[0]}{RESET}")
            print(f"    {GRAY}        :{RESET}  {DIM}deny    {r[0]}{RESET}")
        print()
    except Exception as e:
        err(f"Could not read DB: {e}")

def cmd_resolve(args, decision):
    try:
        r = requests.post(f"{API_BASE}/guard/approvals/{args.action_id}/{decision}", timeout=5)
        r.raise_for_status()
        verb = "approved" if decision == "approve" else "denied"
        ok(f"Action {ORANGE}{args.action_id}{RESET} {verb}.")
    except requests.exceptions.HTTPError as e:
        err(f"Server: {e.response.text}")
    except requests.exceptions.ConnectionError:
        err("Cannot reach AVARA server. Is it running?")
    except Exception as e:
        err(f"Error: {e}")

def cmd_status(args):
    try:
        r = requests.get(f"{API_BASE}/health", timeout=3)
        r.raise_for_status()
        ok(f"AVARA Authority is {GREEN}{BOLD}ONLINE{RESET}  ({API_BASE})")
    except Exception:
        err(f"AVARA Authority is {RED}{BOLD}OFFLINE{RESET}  ({API_BASE})")

    # DB status
    if os.path.exists(DB_PATH):
        size = os.path.getsize(DB_PATH)
        info(f"Database: {DB_PATH} ({size:,} bytes)")
    else:
        warn(f"Database: {DB_PATH} not found (will be created on first use)")

    # Log status
    log_files = sorted(glob.glob(os.path.join(LOG_DIR, "*.log")))
    if log_files:
        info(f"Audit logs: {len(log_files)} file(s) in {LOG_DIR}/")
    else:
        warn(f"Audit logs: none found in {LOG_DIR}/")

def cmd_logs(args):
    tail = getattr(args, 'tail', 20) or 20
    log_files = sorted(glob.glob(os.path.join(LOG_DIR, "*.log")))
    if not log_files:
        warn(f"No audit logs found in {LOG_DIR}/")
        return

    latest = log_files[-1]
    info(f"Showing last {tail} entries from {CYAN}{os.path.basename(latest)}{RESET}\n")

    try:
        with open(latest, 'r') as f:
            lines = f.readlines()
        for line in lines[-tail:]:
            line = line.strip()
            if not line:
                continue
            # Color-code by event type
            if "BLOCK" in line or "DENIED" in line or "REVOKE" in line:
                print(f"    {RED}●{RESET}  {line}")
            elif "ALLOW" in line or "APPROVED" in line or "PROVISION" in line:
                print(f"    {GREEN}●{RESET}  {line}")
            elif "PENDING" in line or "APPROVAL_REQUEST" in line:
                print(f"    {YELLOW}●{RESET}  {line}")
            else:
                print(f"    {GRAY}●{RESET}  {line}")
        print()
    except Exception as e:
        err(f"Could not read log file: {e}")

# ─── Argument Parser (shared by direct + REPL) ───────────────────────────────
def build_parser():
    parser = argparse.ArgumentParser(add_help=False)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("provision")
    p.add_argument("role")
    p.add_argument("desc")
    p.add_argument("--scopes", nargs="+", default=["*"])
    p.add_argument("--ttl", type=int, default=3600)
    p.set_defaults(func=cmd_provision)

    p = sub.add_parser("revoke")
    p.add_argument("agent_id")
    p.set_defaults(func=cmd_revoke)

    sub.add_parser("agents").set_defaults(func=cmd_agents)
    sub.add_parser("pending").set_defaults(func=cmd_pending)

    p = sub.add_parser("approve")
    p.add_argument("action_id")
    p.set_defaults(func=lambda a: cmd_resolve(a, "approve"))

    p = sub.add_parser("deny")
    p.add_argument("action_id")
    p.set_defaults(func=lambda a: cmd_resolve(a, "deny"))

    sub.add_parser("status").set_defaults(func=cmd_status)

    p = sub.add_parser("logs")
    p.add_argument("--tail", type=int, default=20)
    p.set_defaults(func=cmd_logs)

    return parser

# ─── Interactive REPL ─────────────────────────────────────────────────────────
def interactive_mode():
    print_banner()
    print(f"  {CYAN}Interactive mode.{RESET} Type {BOLD}help{RESET} for commands, {BOLD}exit{RESET} to quit.\n")

    parser = build_parser()

    while True:
        try:
            raw = input(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {GRAY}Goodbye.{RESET}\n")
            break

        if not raw:
            continue

        if raw in ("exit", "quit", "q"):
            print(f"  {GRAY}Goodbye.{RESET}\n")
            break

        if raw in ("help", "h", "?"):
            print_help()
            continue

        if raw == "clear":
            os.system("clear" if os.name != "nt" else "cls")
            print_banner()
            continue

        try:
            tokens = shlex.split(raw)
        except ValueError as e:
            err(f"Parse error: {e}")
            continue

        try:
            args = parser.parse_args(tokens)
        except SystemExit:
            err(f"Unknown command: {BOLD}{tokens[0]}{RESET}. Type {BOLD}help{RESET} for available commands.")
            continue

        if not hasattr(args, 'func'):
            err(f"Unknown command: {BOLD}{raw}{RESET}. Type {BOLD}help{RESET} for available commands.")
            continue

        args.func(args)

# ─── Entry Point ──────────────────────────────────────────────────────────────
def main():
    # No arguments → launch interactive mode
    if len(sys.argv) == 1:
        interactive_mode()
        return

    # Help flags
    if sys.argv[1] in ('-h', '--help', 'help'):
        print_help()
        return

    # Version flag
    if sys.argv[1] in ('-v', '--version'):
        print(f"avara-cli v{VERSION}")
        return

    # Direct command mode
    parser = build_parser()
    try:
        args = parser.parse_args()
    except SystemExit:
        err(f"Unknown command. Run {BOLD}./avara_cli.py help{RESET} for usage.")
        sys.exit(1)

    if not hasattr(args, 'func'):
        print_help()
        sys.exit(1)

    print_banner()
    args.func(args)
    print()

if __name__ == "__main__":
    main()
