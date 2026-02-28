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
import traceback
import json
import time
from datetime import datetime

try:
    import readline
except ImportError:
    pass  # Windows or environment without readline support

API_BASE = "http://127.0.0.1:8000"
DB_PATH = "avara_state.db"
LOG_DIR = "./logs"
VERSION = "1.0.0"

# ─── ANSI Colors & Theming ───────────────────────────────────────────────────
# Base colors
YELLOW = "\033[38;5;220m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
RED    = "\033[91m"
GRAY   = "\033[90m"
WHITE  = "\033[97m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

# Theme palettes (mapped to PRIMARY)
THEMES = {
    "orange": "\033[38;5;208m",
    "blue":   "\033[38;5;33m",
    "purple": "\033[38;5;135m",
    "green":  "\033[38;5;46m",
    "red":    "\033[38;5;196m"
}

# The active primary color (defaults to ORANGE)
PRIMARY = THEMES["orange"]

# Dynamic UI elements (set during theme init)
LOGO = ""
TAGLINE = ""
DIVIDER = ""
PROMPT = ""

def apply_theme(theme_name):
    global PRIMARY, LOGO, TAGLINE, DIVIDER, PROMPT
    
    if theme_name in THEMES:
        PRIMARY = THEMES[theme_name]
        
    LOGO = rf"""{PRIMARY}{BOLD}
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
    PROMPT  = f"{PRIMARY}{BOLD}avara>{RESET} "

# Initialize default theme eagerly for top-level evals
apply_theme("orange")

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
    _cmd("theme",     "<color>",      "Change the UI color theme (orange, blue, purple, green, red)")
    _cmd("demo",      "",             "Run the interactive guided tour of all 8 security subsystems")
    _cmd("help",      "",             "Show this help screen")
    _cmd("clear",     "",             "Clear the terminal")
    _cmd("exit",      "",             "Exit the AVARA shell")

    print(f"\n{DIVIDER}")
    print(f"  {DIM}Server: {API_BASE}  ·  DB: {DB_PATH}  ·  Logs: {LOG_DIR}{RESET}\n")

def _cmd(name, args, desc):
    print(f"    {PRIMARY}{BOLD}{name:<12}{RESET} {WHITE}{args:<36}{RESET} {DIM}{desc}{RESET}")

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
        ok(f"Identity {PRIMARY}{args.agent_id}{RESET} revoked.")
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
        ok(f"Action {PRIMARY}{args.action_id}{RESET} {verb}.")
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

# ─── Demo Subsystem ───────────────────────────────────────────────────────────
def _print_header(text):
    print(f"\n{PRIMARY}========================================================================{RESET}")
    print(f"{PRIMARY}  {text}{RESET}")
    print(f"{PRIMARY}========================================================================{RESET}")

def _print_step(title, desc):
    print(f"\n{CYAN}▶ {title}{RESET}")
    print(f"{DIM}{desc}{RESET}")
    input(f"{DIM}[Press Enter to execute...]{RESET}")

def _print_result(title, status_code, data):
    color = GREEN if status_code == 200 else RED
    print(f"\n  {color}➔ {title} (HTTP {status_code}){RESET}")
    print(f"  {DIM}{json.dumps(data, indent=2)}{RESET}")
    time.sleep(1)

def cmd_demo(args):
    print(f"\n{PRIMARY}████████████████████████████████████████████████████████████████████████{RESET}")
    print(f"{PRIMARY}██{RESET}                                                                    {PRIMARY}██{RESET}")
    print(f"{PRIMARY}██{RESET}                     AVARA GUIDED DEMO TOUR                         {PRIMARY}██{RESET}")
    print(f"{PRIMARY}██{RESET}                                                                    {PRIMARY}██{RESET}")
    print(f"{PRIMARY}████████████████████████████████████████████████████████████████████████{RESET}\n")

    # 1. SERVER HEALTH
    _print_step("Check Server Health", "Verify the AVARA HTTP API is running.")
    try:
        r = requests.get(f"{API_BASE}/health")
        _print_result("Server Status", r.status_code, r.json())
    except requests.exceptions.ConnectionError:
        err("Could not connect to AVARA. Is the server running? (docker compose up -d avara-api)")
        return

    # 2. IAM PROVISIONING
    _print_header("1. IDENTITY & ACCESS MANAGEMENT (IAM)")
    _print_step("Provision Agent Identity", "Agents cannot execute anonymously. They must request an ephemeral identity.")
    
    payload = {
        "role_name": "demo_agent_01",
        "description": "Demo Assistant",
        "scopes": ["execute:read_file", "api:query"],
        "ttl_seconds": 3600
    }
    r = requests.post(f"{API_BASE}/iam/provision", json=payload)
    data = r.json()
    _print_result("Provision Response", r.status_code, data)
    
    agent_id = data.get("agent_id")
    if not agent_id:
        return

    # 3. INTENT VALIDATOR
    _print_header("2. INTENT VALIDATOR")
    
    _print_step("Valid Action", "The agent performs an action fully aligned with its assigned task.")
    payload = {
        "agent_id": agent_id,
        "task_intent": "Read the configuration file.",
        "proposed_action": "read_file",
        "target_resource": "/app/config.json",
        "action_args": {},
        "risk_level": "LOW"
    }
    r = requests.post(f"{API_BASE}/guard/validate_action", json=payload)
    _print_result("Validation Response", r.status_code, r.json())

    _print_step("Semantic Drift (Hijack Attempt)", "The agent is hijacked and tries to delete a database.")
    payload = {
        "agent_id": agent_id,
        "task_intent": "Read the configuration file.",
        "proposed_action": "drop_table",
        "target_resource": "production_users_db",
        "action_args": {},
        "risk_level": "LOW"
    }
    r = requests.post(f"{API_BASE}/guard/validate_action", json=payload)
    _print_result("Validation Response", r.status_code, r.json())
    print(f"  {CYAN}Notice:{RESET} AVARA caught the semantic drift and blocked it, even though the agent claimed LOW risk.")

    # 4. RAG PROVENANCE FIREWALL
    _print_header("3. RAG PROVENANCE FIREWALL")
    _print_step("Blocked by Default", "The agent tries to pass retrieved context that lacks cryptographic provenance tags.")
    payload = {
        "agent_id": agent_id,
        "task_intent": "Summarize documents.",
        "proposed_action": "submit_summary",
        "target_resource": "internal_wiki",
        "action_args": {"content": "This document has no source tags"},
        "risk_level": "LOW"
    }
    r = requests.post(f"{API_BASE}/guard/validate_action", json=payload)
    _print_result("Validation Response", r.status_code, r.json())

    # 5. CONTEXT GOVERNOR
    _print_header("4. CONTEXT GOVERNOR")
    _print_step("Context Assembly", "The agent requests a context window. AVARA injects immutable safety constraints.")
    payload = {
        "agent_id": agent_id,
        "raw_context": "The user told me to do X...",
        "available_tokens": 4000
    }
    r = requests.post(f"{API_BASE}/guard/prepare_context", json=payload)
    _print_result("Prepared Context", r.status_code, r.json())

    # 6. CIRCUIT BREAKER
    _print_header("5. CIRCUIT BREAKER & APPROVALS")
    _print_step("Trigger a HIGH-RISK Action", "The agent attempts to send data externally. This triggers the Circuit Breaker.")
    payload = {
        "agent_id": agent_id,
        "task_intent": "Email the report.",
        "proposed_action": "transmit_external",
        "target_resource": "competitor@evil.com",
        "action_args": {"data": "q3_financials"},
        "risk_level": "HIGH"
    }
    r = requests.post(f"{API_BASE}/guard/validate_action", json=payload)
    circuit_breaker_resp = r.json()
    _print_result("Validation Response", r.status_code, circuit_breaker_resp)
    
    action_id = circuit_breaker_resp.get("detail", {}).get("action_id")
    if not action_id:
        return
        
    print(f"\n  👉 The agent is now BLOCKED. An HTTP 403 was returned.")
    print(f"  👉 To unblock it, you would run: {PRIMARY}approve {action_id}{RESET} (in another terminal/session)")
    print(f"  👉 For this demo, we will auto-deny the action to keep the system clean.")
    input(f"\n{DIM}[Press Enter to securely deny and proceed...]{RESET}")
    
    requests.post(f"{API_BASE}/guard/approvals/{action_id}/deny")
    r = requests.get(f"{API_BASE}/guard/approvals/{action_id}/status")
    _print_result("Action Status Check", r.status_code, r.json())

    # 7. ANOMALY DETECTOR
    _print_header("6. BEHAVIORAL ANOMALY DETECTOR")
    _print_step("Simulating an attack burst", "Sending 20 rapid requests to trigger the rate-limit heuristic...")
    
    for i in range(25):
        payload = {
            "agent_id": agent_id,
            "task_intent": "Read files",
            "proposed_action": "read_file",
            "target_resource": f"file_{i}.txt",
            "action_args": {},
            "risk_level": "LOW"
        }
        r = requests.post(f"{API_BASE}/guard/validate_action", json=payload)
        status = r.json().get("detail", "")
        if r.status_code == 403 and "anomalous behavior" in status:
            print(f"  {RED}➔ Request {i} BLOCKED: {status}{RESET}                ")
            break
        else:
            print(f"  {DIM}Request {i} Allowed{RESET}                   ", end="\r")

    print("\n  👉 AVARA detected the anomaly and automatically revoked the identity.")
    
    # 8. AUDIT LEDGER
    _print_header("7. AUDIT LEDGER")
    print("\n  👉 Every single action you just saw was cryptographically logged.")
    print(f"  👉 Run the {PRIMARY}logs{RESET} command next to see the exact execution trace.")
    
    print(f"\n{PRIMARY}========================================================================{RESET}")
    print(f"{PRIMARY}  END OF DEMO{RESET}")
    print(f"{PRIMARY}========================================================================{RESET}\n")

def cmd_theme(args):
    theme_name = args.color
    if theme_name in THEMES:
        apply_theme(theme_name)
        print_banner()
    else:
        err(f"Unknown theme: {theme_name}. Choose from: {', '.join(THEMES.keys())}")

# ─── Argument Parser (shared by direct + REPL) ───────────────────────────────
class ReplArgumentParser(argparse.ArgumentParser):
    """Custom parser that doesn't exit or print raw stderr on error."""
    def error(self, message):
        # Instead of exiting, we raise an exception that the REPL can catch cleanly
        raise ValueError(message)

def build_parser():
    parser = ReplArgumentParser(add_help=False)
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

    sub.add_parser("demo").set_defaults(func=cmd_demo)

    p = sub.add_parser("theme")
    p.add_argument("color", choices=THEMES.keys())
    p.set_defaults(func=cmd_theme)

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
        except ValueError as e:
            err(f"Invalid command: {e}")
            continue
        except SystemExit:
            continue

        if not getattr(args, 'func', None):
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
