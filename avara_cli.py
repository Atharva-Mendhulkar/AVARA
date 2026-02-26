#!/usr/bin/env python3
import argparse
import requests
import sqlite3
import sys
from datetime import datetime

API_BASE = "http://127.0.0.1:8000"
DB_PATH = "avara_state.db"

# ─── ANSI Colors ─────────────────────────────────────────────────────────────
ORANGE = "\033[38;5;208m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
RED    = "\033[91m"
GRAY   = "\033[90m"
WHITE  = "\033[97m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

# ─── ASCII Logo (Orange) ──────────────────────────────────────────────────────
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

TAGLINE = f"{GRAY}  Autonomous Validation & Agent Risk Authority  ·  Runtime Security CLI{RESET}"
DIVIDER = f"{GRAY}{'─' * 60}{RESET}"

# ─── Helpers ──────────────────────────────────────────────────────────────────
def ok(msg):  print(f"  {GREEN}✔{RESET}  {msg}")
def err(msg): print(f"  {RED}✖{RESET}  {msg}")
def hdr(msg): print(f"\n{CYAN}{BOLD}{msg}{RESET}")

def print_banner():
    print(LOGO)
    print(TAGLINE)
    print()

def print_full_help():
    print_banner()
    print(DIVIDER)

    hdr("COMMANDS")
    print()

    cmds = [
        ("provision", "<role> <desc> [--scopes ...] [--ttl N]",
         "Provision a new ephemeral Agent Identity.",
         [
            ('Example', './avara_cli.py provision prod_agent "Marketing Bot" --scopes execute:read_file api:query --ttl 3600'),
         ]),
        ("revoke", "<agent_id>",
         "Immediately revoke an active Agent Identity.",
         [
            ('Example', './avara_cli.py revoke agt_d263945d'),
         ]),
        ("pending", "",
         "List all HIGH-RISK actions halted by the Circuit Breaker.",
         [
            ('Example', './avara_cli.py pending'),
         ]),
        ("approve", "<action_id>",
         "Grant human approval for a halted action – agent is unblocked.",
         [
            ('Example', './avara_cli.py approve 876fa285-9a38-4785-8d6b-fb4d942765e6'),
         ]),
        ("deny", "<action_id>",
         "Permanently deny a halted action – agent stays blocked.",
         [
            ('Example', './avara_cli.py deny 876fa285-9a38-4785-8d6b-fb4d942765e6'),
         ]),
        ("status", "",
         "Check the AVARA API server health.",
         [
            ('Example', './avara_cli.py status'),
         ]),
    ]

    for name, usage, desc, examples in cmds:
        print(f"  {ORANGE}{BOLD}{name:<12}{RESET}  {WHITE}{usage}{RESET}")
        print(f"  {DIM}{' ' * 14}{desc}{RESET}")
        for label, ex in examples:
            print(f"  {GRAY}{' ' * 14}$ {ex}{RESET}")
        print()

    print(DIVIDER)
    print(f"  {DIM}API Server: {API_BASE}   ·   DB: {DB_PATH}{RESET}")
    print()

# ─── Command Handlers ─────────────────────────────────────────────────────────
def cmd_provision(args):
    payload = {
        "role_name":   args.role,
        "description": args.desc,
        "scopes":      args.scopes,
        "ttl_seconds": args.ttl
    }
    try:
        r = requests.post(f"{API_BASE}/iam/provision", json=payload)
        r.raise_for_status()
        d = r.json()
        ok(f"Identity provisioned")
        print(f"  {GRAY}Agent ID : {WHITE}{d['agent_id']}{RESET}")
        print(f"  {GRAY}Role     : {WHITE}{args.role}{RESET}")
        print(f"  {GRAY}Scopes   : {WHITE}{', '.join(d['scopes'])}{RESET}")
        print(f"  {GRAY}TTL      : {WHITE}{d['ttl']}s{RESET}")
    except requests.exceptions.ConnectionError:
        err("Cannot reach AVARA server. Is it running?")
    except Exception as e:
        err(f"Provisioning failed: {e}")

def cmd_revoke(args):
    try:
        r = requests.delete(f"{API_BASE}/iam/revoke/{args.agent_id}")
        r.raise_for_status()
        ok(f"Identity {ORANGE}{args.agent_id}{RESET} revoked.")
    except requests.exceptions.ConnectionError:
        err("Cannot reach AVARA server. Is it running?")
    except Exception as e:
        err(f"Revocation failed: {e}")

def cmd_pending(args):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT action_id, agent_id, action_type, target, timestamp "
                "FROM approvals WHERE status = 'PENDING'"
            ).fetchall()

        if not rows:
            print(f"\n  {GRAY}No pending approvals. All clear.{RESET}\n")
            return

        print(f"\n  {ORANGE}{BOLD}PENDING CIRCUIT BREAKER APPROVALS{RESET}  ({len(rows)} item{'s' if len(rows)>1 else ''})\n")
        for r in rows:
            dt = datetime.fromtimestamp(r[4]).strftime('%Y-%m-%d %H:%M:%S')
            print(f"  {GRAY}{'─'*54}{RESET}")
            print(f"  {CYAN}Action ID{RESET}  {r[0]}")
            print(f"  {GRAY}Agent   :{RESET}  {r[1]}")
            print(f"  {GRAY}Action  :{RESET}  {RED}{r[2]}{RESET}  →  {r[3]}")
            print(f"  {GRAY}Halted  :{RESET}  {dt}")
            print(f"\n  {GRAY}  → approve: {WHITE}./avara_cli.py approve {r[0]}{RESET}")
            print(f"  {GRAY}  →    deny: {WHITE}./avara_cli.py deny    {r[0]}{RESET}\n")
    except Exception as e:
        err(f"Could not read DB: {e}")

def cmd_resolve(args, decision):
    try:
        r = requests.post(f"{API_BASE}/guard/approvals/{args.action_id}/{decision}")
        r.raise_for_status()
        verb = "approved" if decision == "approve" else "denied"
        ok(f"Action {ORANGE}{args.action_id}{RESET} {verb}.")
    except requests.exceptions.HTTPError as e:
        err(f"Server responded: {e.response.text}")
    except requests.exceptions.ConnectionError:
        err("Cannot reach AVARA server. Is it running?")
    except Exception as e:
        err(f"Error: {e}")

def cmd_status(args):
    try:
        r = requests.get(f"{API_BASE}/health", timeout=3)
        r.raise_for_status()
        ok(f"AVARA Authority is {GREEN}ONLINE{RESET}  ({API_BASE})")
    except Exception:
        err(f"AVARA Authority is {RED}OFFLINE{RESET}  ({API_BASE})")

# ─── Entry Point ──────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) == 1:
        print_full_help()
        sys.exit(0)

    if sys.argv[1] in ('-h', '--help', 'help'):
        print_full_help()
        sys.exit(0)

    parser = argparse.ArgumentParser(add_help=False)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("provision");  p.add_argument("role"); p.add_argument("desc")
    p.add_argument("--scopes", nargs="+", default=["*"]); p.add_argument("--ttl", type=int, default=3600)
    p.set_defaults(func=cmd_provision)

    p = sub.add_parser("revoke"); p.add_argument("agent_id"); p.set_defaults(func=cmd_revoke)
    p = sub.add_parser("pending"); p.set_defaults(func=cmd_pending)
    p = sub.add_parser("approve"); p.add_argument("action_id"); p.set_defaults(func=lambda a: cmd_resolve(a, "approve"))
    p = sub.add_parser("deny");    p.add_argument("action_id"); p.set_defaults(func=lambda a: cmd_resolve(a, "deny"))
    p = sub.add_parser("status");  p.set_defaults(func=cmd_status)

    args = parser.parse_args()
    if not hasattr(args, 'func'):
        print_full_help()
        sys.exit(1)

    print_banner()
    args.func(args)
    print()

if __name__ == "__main__":
    main()
