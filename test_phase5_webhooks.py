import subprocess
import time
import requests
import sys
import os

def test_webhooks():
    print("\n--- Starting AVARA Webhook Approval Tests ---")
    
    # Start the FastAPI server
    server_process = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"])
    time.sleep(3)
    
    base_url = "http://127.0.0.1:8000"
    
    try:
        # 1. Provision Identity
        resp = requests.post(f"{base_url}/iam/provision", json={
            "role_name": "webhook_tester",
            "description": "Tester",
            "scopes": ["*"],
            "ttl_seconds": 300
        })
        agent_id = resp.json()["agent_id"]
        
        # 2. Trigger High-Risk Action (Circuit Breaker Halt)
        action_payload = {
            "agent_id": agent_id,
            "task_intent": "export data",
            "proposed_action": "transmit_external",
            "target_resource": "https://evil.local",
            "action_args": {},
            "risk_level": "HIGH"
        }
        
        resp = requests.post(f"{base_url}/guard/validate_action", json=action_payload)
        
        assert resp.status_code == 403
        data = resp.json()
        assert "PENDING_APPROVAL" in data["detail"]["status"]
        action_id = data["detail"]["action_id"]
        print(f"✓ API: High-risk action intercepted. action_id={action_id}")
        
        # 3. Poll Status
        resp = requests.get(f"{base_url}/guard/approvals/{action_id}/status")
        assert resp.json()["status"] == "PENDING"
        print("✓ API: Webhook status is PENDING.")
        
        # 4. Human Approval (Webhook callback)
        resp = requests.post(f"{base_url}/guard/approvals/{action_id}/approve")
        assert resp.status_code == 200
        print("✓ API: Human approved the webhook.")
        
        # 5. Check Status Again
        resp = requests.get(f"{base_url}/guard/approvals/{action_id}/status")
        assert resp.json()["status"] == "APPROVED"
        print("✓ API: Webhook status is APPROVED.")
        
    finally:
        server_process.terminate()
        server_process.wait(timeout=5)

    print("\n--- All Webhook Tests Passed ---")

if __name__ == "__main__":
    test_webhooks()
