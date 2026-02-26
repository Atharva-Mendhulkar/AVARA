from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import time

# Import AVARA guard systems
from src.guards.tool_guard import ToolRegistry, ToolGuard, ToolRegistration, ToolPermission
from src.guards.circuit_breaker import CircuitBreaker, AgentAction, ActionRiskLevel, CircuitBreakerStatus
from src.core.audit_ledger import AuditLedger
from src.core.iam_service import IAMService, AgentRole
from src.guards.rag_firewall import RAGFirewall, DocumentProvenance
from src.guards.intent_validator import IntentValidator, AgentState, ValidationDecision
from src.guards.multi_agent_monitor import MultiAgentMonitor, AgentMessage
from src.guards.context_governor import ContextGovernor
from src.guards.anomaly_detector import AnomalyDetector
from src.db.persistent_store import PersistentStore
import uuid

# Persistent DB connection
persistent_store = PersistentStore()

# Import AVARA guard systems (using in-memory instances where DB not fully retrofitted yet)
iam_service = IAMService()
tool_registry = ToolRegistry()
tool_guard = ToolGuard(tool_registry)
circuit_breaker = CircuitBreaker()
audit_ledger = AuditLedger(log_dir="./logs")
rag_firewall = RAGFirewall()
intent_validator = IntentValidator()
multi_agent_monitor = MultiAgentMonitor()
context_governor = ContextGovernor()
anomaly_detector = AnomalyDetector()

app = FastAPI(title="AVARA Control Plane", description="Runtime Authority API for Autonomous Agents", version="0.1.0")

# ----------------- Models -----------------

class ProvisionIdentityRequest(BaseModel):
    role_name: str
    description: str
    scopes: List[str]
    ttl_seconds: int = 3600

class ValidateActionRequest(BaseModel):
    agent_id: str
    task_intent: str
    proposed_action: str
    target_resource: str
    action_args: Dict[str, Any]
    risk_level: str  # "LOW", "MEDIUM", "HIGH"

class ContextPreparationRequest(BaseModel):
    agent_id: str
    dynamic_query: str
    system_prompt: str

# ----------------- Middlewares / Dependency -----------------
def get_verified_agent(agent_id: str):
    """Enforce IAM checks on every protected route."""
    try:
        identity = iam_service.validate_agent(agent_id)
        # Check anomaly
        if anomaly_detector.detect_anomalies(agent_id):
            iam_service.revoke_identity(agent_id)
            raise HTTPException(status_code=403, detail="Agent identity revoked due to anomalous behavior.")
        return identity
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))

# ----------------- Routes: IAM & Identity -----------------

@app.post("/iam/provision")
def provision_agent(request: ProvisionIdentityRequest):
    """Provisions a new ephemeral identity for an agent run."""
    role = AgentRole(request.role_name, request.description)
    identity = iam_service.provision_identity(role, request.scopes, request.ttl_seconds)
    audit_ledger.log_event("IAM_PROVISION", identity.agent_id, request.model_dump())
    return {"agent_id": identity.agent_id, "ttl": identity.token_ttl_seconds, "scopes": list(identity.scopes)}

@app.delete("/iam/revoke/{agent_id}")
def revoke_agent(agent_id: str):
    iam_service.revoke_identity(agent_id)
    audit_ledger.log_event("IAM_REVOKE", agent_id, {})
    return {"status": "success", "message": f"Identity {agent_id} revoked."}

# ----------------- Routes: Execution Guards -----------------

@app.post("/guard/validate_action")
def validate_agent_action(request: ValidateActionRequest):
    """The main interceptor endpoint an agent hits before executing ANY tool/action."""
    
    # 1. IAM & Anomaly Check
    identity = get_verified_agent(request.agent_id)
    anomaly_detector.log_execution(request.agent_id, request.proposed_action, request.target_resource)
    
    # 2. Intent Validation (Check for drift)
    state = AgentState(request.task_intent, request.proposed_action, request.target_resource, request.action_args)
    intent_decision = intent_validator.validate_action(state)
    
    if intent_decision == ValidationDecision.BLOCK:
        audit_ledger.log_event("INTENT_BLOCK", request.agent_id, request.model_dump())
        raise HTTPException(status_code=403, detail="Blocked: Severe semantic drift detected from assigned task intent.")

    # 3. Tool explicitly registered and permissions match?
    # Simple mock check for tool execution if action is a tool call
    if tool_registry.is_registered(request.proposed_action):
        agent_perms = [ToolPermission(s.split(":")[0], s.split(":")[1] if ":" in s else "*", "") for s in identity.scopes]
        if not tool_guard.validate_invocation(request.proposed_action, request.action_args, agent_perms):
            raise HTTPException(status_code=403, detail="Blocked: Tool invocation failed permission or schema validation.")

    # 4. Excessive-Agency Circuit Breaker
    risk_enum = ActionRiskLevel[request.risk_level.upper()]
    action = AgentAction(request.proposed_action, request.target_resource, request.action_args, risk_enum)
    
    breaker_status = circuit_breaker.evaluate_action(action)
    if breaker_status == CircuitBreakerStatus.HALT_REQUIRE_APPROVAL:
        action_id = str(uuid.uuid4())
        # Store pending approval in DB
        persistent_store.save_approval(action_id, request.agent_id, request.proposed_action, request.target_resource, request.action_args, "PENDING")
        audit_ledger.log_approval_request(request.agent_id, request.proposed_action, request.target_resource, "PENDING")
        
        # Simulate firing off an async webhook to a designated channel (Slack, Email, etc.)
        print(f"\n[WEBHOOK TRIGGERED] Action {action_id} requires human approval.")
        print(f"--> POST /slack/avara-alerts payload=... \n")
        
        # We return 403 but with a specific detail object dictating that it is pending approval
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail={
                "error": "Blocked: High-risk action halted by Circuit Breaker. Human approval required.",
                "action_id": action_id,
                "status": "PENDING_APPROVAL"
            }
        )

    # If all passes
    audit_ledger.log_event("ACTION_ALLOW", request.agent_id, request.model_dump())
    return {"status": "allowed"}

# ----------------- Routes: Webhook Approvals -----------------
@app.post("/guard/approvals/{action_id}/approve")
def approve_action(action_id: str):
    """External webhook callback to approve a pending action."""
    approval = persistent_store.get_approval(action_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    if approval["status"] != "PENDING":
        raise HTTPException(status_code=400, detail=f"Action is already {approval['status']}.")
        
    persistent_store.update_approval_status(action_id, "APPROVED")
    audit_ledger.log_event("APPROVAL_GRANTED", approval["agent_id"], {"action_id": action_id})
    return {"status": "success", "message": f"Action {action_id} approved. Agent may proceed."}

@app.post("/guard/approvals/{action_id}/deny")
def deny_action(action_id: str):
    """External webhook callback to deny a pending action."""
    approval = persistent_store.get_approval(action_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    if approval["status"] != "PENDING":
        raise HTTPException(status_code=400, detail=f"Action is already {approval['status']}.")
        
    persistent_store.update_approval_status(action_id, "DENIED")
    audit_ledger.log_event("APPROVAL_DENIED", approval["agent_id"], {"action_id": action_id})
    return {"status": "success", "message": f"Action {action_id} strictly denied."}

@app.get("/guard/approvals/{action_id}/status")
def check_approval_status(action_id: str):
    """Agents can poll this endpoint to see if they were approved to proceed."""
    approval = persistent_store.get_approval(action_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    return {"action_id": action_id, "status": approval["status"]}

# ----------------- Routes: Context & RAG -----------------

@app.post("/guard/prepare_context")
def prepare_context(request: ContextPreparationRequest):
    """Enforces token budget and mandatory safety anchors for prompt generation."""
    get_verified_agent(request.agent_id)
    context = context_governor.prepare_context(request.dynamic_query, request.system_prompt)
    
    if not context:
        audit_ledger.log_event("CONTEXT_SATURATION_BLOCK", request.agent_id, {"dynamic_query_length": len(request.dynamic_query)})
        raise HTTPException(status_code=413, detail="Blocked: Context saturation limits exceeded.")
        
    return {
        "budget_used": context.tokens_used,
        "safety_anchors": context.safety_anchors,
        "final_context_block": "\n".join(context.safety_anchors) + f"\n\n{request.system_prompt}\n\n{request.dynamic_query}"
    }

@app.get("/health")
def health_check():
    return {"status": "AVARA Central Authority is online."}
