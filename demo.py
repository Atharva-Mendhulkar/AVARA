#!/usr/bin/env python3
"""
AVARA Interactive Demo Client
A guided tour of all 8 core runtime guards in the AVARA security system.

Prerequisites:
  1. Have the AVARA server running (docker compose up -d avara-api)
  2. Have the AVARA CLI ready in another terminal (./avara_cli.py)
"""
import requests
import json
import time

API_BASE = "http://127.0.0.1:8000"

# ANSI Colors
ORANGE = "\033[38;5;208m"
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"

def print_header(text):
    print(f"\n{ORANGE}========================================================================{RESET}")
    print(f"{ORANGE}  {text}{RESET}")
    print(f"{ORANGE}========================================================================{RESET}")

def print_step(title, desc):
    print(f"\n{CYAN}▶ {title}{RESET}")
    print(f"{DIM}{desc}{RESET}")
    input(f"{DIM}[Press Enter to execute...]{RESET}")

def print_result(title, status_code, data):
    color = GREEN if status_code == 200 else RED
    print(f"\n  {color}➔ {title} (HTTP {status_code}){RESET}")
    print(f"  {DIM}{json.dumps(data, indent=2)}{RESET}")
    time.sleep(1)

def run_demo():
    print(f"\n{ORANGE}████████████████████████████████████████████████████████████████████████{RESET}")
    print(f"{ORANGE}██{RESET}                                                                    {ORANGE}██{RESET}")
    print(f"{ORANGE}██{RESET}                     AVARA GUIDED DEMO TOUR                         {ORANGE}██{RESET}")
    print(f"{ORANGE}██{RESET}                                                                    {ORANGE}██{RESET}")
    print(f"{ORANGE}████████████████████████████████████████████████████████████████████████{RESET}\n")

    # ---------------------------------------------------------
    # 1. SERVER HEALTH
    # ---------------------------------------------------------
    print_step("Check Server Health", "Verify the AVARA HTTP API is running.")
    try:
        r = requests.get(f"{API_BASE}/health")
        print_result("Server Status", r.status_code, r.json())
    except requests.exceptions.ConnectionError:
        print(f"\n{RED}✖ Could not connect to AVARA. Is the server running?{RESET}")
        print("Run: docker compose up -d avara-api")
        return

    # ---------------------------------------------------------
    # 2. IAM PROVISIONING (Identity & Access Management)
    # ---------------------------------------------------------
    print_header("1. IDENTITY & ACCESS MANAGEMENT (IAM)")
    print_step("Provision Agent Identity", "Agents cannot execute anonymously. They must request an ephemeral identity.")
    
    payload = {
        "role_name": "demo_agent_01",
        "description": "Demo Assistant",
        "scopes": ["execute:read_file", "api:query"],
        "ttl_seconds": 3600
    }
    r = requests.post(f"{API_BASE}/iam/provision", json=payload)
    data = r.json()
    print_result("Provision Response", r.status_code, data)
    
    agent_id = data.get("agent_id")
    if not agent_id:
        return

    # ---------------------------------------------------------
    # 3. INTENT VALIDATOR (Semantic Drift)
    # ---------------------------------------------------------
    print_header("2. INTENT VALIDATOR")
    
    print_step("Valid Action", "The agent performs an action fully aligned with its assigned task.")
    payload = {
        "agent_id": agent_id,
        "task_intent": "Read the configuration file.",
        "proposed_action": "read_file",
        "target_resource": "/app/config.json",
        "action_args": {},
        "risk_level": "LOW"
    }
    r = requests.post(f"{API_BASE}/guard/validate_action", json=payload)
    print_result("Validation Response", r.status_code, r.json())

    print_step("Semantic Drift (Hijack Attempt)", "The agent was told to read a config file, but tries to delete a user database (classic prompt injection).")
    payload = {
        "agent_id": agent_id,
        "task_intent": "Read the configuration file.",
        "proposed_action": "drop_table",
        "target_resource": "production_users_db",
        "action_args": {},
        "risk_level": "LOW" # Notice the agent tries to claim it's low risk
    }
    r = requests.post(f"{API_BASE}/guard/validate_action", json=payload)
    print_result("Validation Response", r.status_code, r.json())
    print(f"  {CYAN}Notice:{RESET} AVARA caught the semantic drift and blocked it, even though the agent claimed LOW risk.")

    # ---------------------------------------------------------
    # 4. RAG PROVENANCE FIREWALL
    # ---------------------------------------------------------
    print_header("3. RAG PROVENANCE FIREWALL")
    print_step("Blocked by Default", "The agent tries to pass retrieved context that lacks cryptographic provenance tags.")
    payload = {
        "agent_id": agent_id,
        "task_intent": "Summarize documents.",
        "proposed_action": "submit_summary",
        "target_resource": "internal_wiki",
        "action_args": {"content": "This document has no source tags"},
        "risk_level": "LOW"
    }
    r = requests.post(f"{API_BASE}/guard/validate_action", json=payload)
    print_result("Validation Response", r.status_code, r.json())

    # ---------------------------------------------------------
    # 5. CONTEXT GOVERNOR
    # ---------------------------------------------------------
    print_header("4. CONTEXT GOVERNOR")
    print_step("Context Assembly", "The agent requests a context window. AVARA injects immutable safety constraints at the top before execution.")
    payload = {
        "agent_id": agent_id,
        "raw_context": "The user told me to do X...",
        "available_tokens": 4000
    }
    r = requests.post(f"{API_BASE}/guard/prepare_context", json=payload)
    print_result("Prepared Context", r.status_code, r.json())

    # ---------------------------------------------------------
    # 6. CIRCUIT BREAKER & WEBHOOKS
    # ---------------------------------------------------------
    print_header("5. CIRCUIT BREAKER & APPROVALS")
    print_step("Trigger a HIGH-RISK Action", "The agent attempts to send data externally. This triggers the Circuit Breaker.")
    payload = {
        "agent_id": agent_id,
        "task_intent": "Email the report.",
        "proposed_action": "transmit_external", # A known HIGH risk action
        "target_resource": "competitor@evil.com",
        "action_args": {"data": "q3_financials"},
        "risk_level": "HIGH"
    }
    r = requests.post(f"{API_BASE}/guard/validate_action", json=payload)
    circuit_breaker_resp = r.json()
    print_result("Validation Response", r.status_code, circuit_breaker_resp)
    
    action_id = circuit_breaker_resp.get("action_id")
    
    print("\n  👉 The agent is now BLOCKED. An HTTP 403 was returned.")
    print(f"  👉 Open a new terminal and run: {ORANGE}./avara_cli.py pending{RESET}")
    print(f"  👉 Then approve it using:       {ORANGE}./avara_cli.py approve {action_id}{RESET}")
    input(f"\n{DIM}[Press Enter AFTER you have approved the action in the CLI...]{RESET}")

    # Check status
    r = requests.get(f"{API_BASE}/guard/approvals/{action_id}/status")
    print_result("Action Status Check", r.status_code, r.json())

    # ---------------------------------------------------------
    # 7. ANOMALY DETECTOR
    # ---------------------------------------------------------
    print_header("6. BEHAVIORAL ANOMALY DETECTOR")
    print_step("Simulating an attack burst", "Sending 20 rapid requests to trigger the rate-limit heuristic...")
    
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
        status = r.json().get("status")
        if status == "BLOCKED":
            print(f"  {RED}➔ Request {i} BLOCKED: {r.json().get('error')}{RESET}")
            break
        else:
            print(f"  {DIM}Request {i} Allowed{RESET}", end="\r")

    print("\n  👉 AVARA detected the anomaly and automatically revoked the identity.")
    
    # Verify revocation
    print_step("Verify Revocation", "Attempting one more normal action. It should be blocked because the agent identity was revoked.")
    payload = {
        "agent_id": agent_id,
        "task_intent": "Read files",
        "proposed_action": "read_file",
        "target_resource": "/app/config.json",
        "action_args": {},
        "risk_level": "LOW"
    }
    r = requests.post(f"{API_BASE}/guard/validate_action", json=payload)
    print_result("Validation Response", r.status_code, r.json())

    # ---------------------------------------------------------
    # 8. AUDIT LEDGER
    # ---------------------------------------------------------
    print_header("7. AUDIT LEDGER")
    print("\n  👉 Every single action you just saw was cryptographically logged.")
    print(f"  👉 Open your CLI terminal and run: {ORANGE}./avara_cli.py logs{RESET}")
    
    print(f"\n{ORANGE}========================================================================{RESET}")
    print(f"{ORANGE}  END OF DEMO{RESET}")
    print(f"{ORANGE}========================================================================{RESET}\n")

if __name__ == "__main__":
    run_demo()
