# AVARA - Autonomous Validation & Agent Risk Authority
![AVARA](assets/avara_logo.png)
> **AVARA is a runtime security and governance system for autonomous AI agents.**
> It enforces intent, permissions, provenance, and safety **at execution time**, not at training time.

---

## Why AVARA Exists

AI agents crossed a boundary in 2024–2026: from assistive to **autonomous**, from human-paced to **machine-speed**, from single-model to **multi-agent + tool ecosystems**.

Security did not evolve with this shift. Existing controls (WAF, IAM, RBAC, DLP) assume human decision points, static APIs, and deterministic software. AI agents violate all three.

AVARA introduces a new control layer — an **always-on runtime authority** that sits between agents and the world.

---

## System Architecture

```mermaid
graph TD
    U["User / System"] --> AF["Agent Framework<br/>(LangGraph / CrewAI / AutoGen)"]
    AF --> AVARA

    subgraph AVARA["AVARA Runtime Authority"]
        IAM["Agent IAM"]
        IV["Intent Validator"]
        RF["RAG Provenance Firewall"]
        TG["Tool & MCP Execution Guard"]
        CB["Excessive-Agency Circuit Breaker"]
        CG["Context Governor"]
        AD["Anomaly Detector (Async)"]
        AL["Audit & Forensics Ledger"]
    end

    IAM --> IV
    IV --> RF
    RF --> TG
    TG --> CB
    CB --> CG

    IAM --> AL
    IV --> AL
    RF --> AL
    TG --> AL
    CB --> AL
    CG --> AL

    AL --> AD

    CG --> LLM["LLMs"]
    CG --> VDB["Vector DBs (Untrusted)"]
    CG --> MCP["MCP / Tools"]
    CG --> API["External APIs"]

    style AVARA fill:#1a1a2e,stroke:#e67e22,stroke-width:2px,color:#fff
```

---

## Secure Agent Execution Flow

```mermaid
sequenceDiagram
    actor User
    participant Agent
    participant AVARA
    participant Tool
    participant Audit as Audit Ledger
    participant Human

    User->>Agent: Issues Task
    Agent->>AVARA: Request Action

    AVARA->>AVARA: Authenticate Agent (IAM)
    AVARA->>AVARA: Validate Intent
    AVARA->>AVARA: Check Permissions
    AVARA->>AVARA: Evaluate Risk
    AVARA->>Audit: Write Decision Record

    alt Low Risk — Allowed
        AVARA->>Tool: Execute Tool Call
        Tool->>Agent: Return Result
        AVARA->>Audit: Log Execution Result
    else High Risk — Halted
        AVARA->>Audit: Persist Action (PENDING)
        AVARA-->>Agent: 403 PENDING_APPROVAL
        AVARA->>Human: Webhook Notification

        alt Approved
            Human->>AVARA: Approve Action
            AVARA->>Tool: Execute Tool Call
            Tool->>Agent: Return Result
            AVARA->>Audit: Log Approved Execution
        else Denied
            Human->>AVARA: Deny Action
            AVARA->>Audit: Log Permanent Denial
            AVARA-->>Agent: Action Blocked
        end
    end
```

---

## Circuit Breaker Webhook Flow

```mermaid
flowchart LR
    A["Agent Action<br/>(HIGH Risk)"] --> CB["Circuit Breaker"]

    CB --> DB["SQLite: Actions Table<br/>(status = PENDING)"]
    CB --> WH["Fire Webhook<br/>(Slack / Email / CLI)"]
    CB --> R403["Return 403<br/>+ action_id"]

    WH --> HR["Human Review"]

    HR -->|Approve| AP["POST /approvals/{id}/approve"]
    HR -->|Deny| DN["POST /approvals/{id}/deny"]

    AP --> DB2["Update Action<br/>(status = APPROVED)"]
    DN --> DB3["Update Action<br/>(status = DENIED)"]

    style CB fill:#e74c3c,stroke:#c0392b,color:#fff
    style DB fill:#2d2d44,stroke:#e67e22,color:#fff
    style R403 fill:#e67e22,stroke:#d35400,color:#fff
```

---

## Core Components

| Component | What It Does |
|---|---|
| **Intent Validator** | Compares user intent vs agent action. Detects semantic drift and blocks instruction hijacking. |
| **RAG Provenance Firewall** | Enforces document identity & ACLs. Prevents permission bypass via retrieval. Scans for latent instructions. |
| **Tool & MCP Execution Guard** | Registers tools explicitly. Validates metadata and enforces per-tool permissions. |
| **Circuit Breaker** | Detects destructive actions. Requires human approval via async webhooks. Prevents zero-click attacks. |
| **Agent IAM** | Ephemeral identity, role, permission scope, and token TTL per agent. No anonymous execution. |
| **Multi-Agent Monitor** | Logs agent-to-agent messages. Tracks assumption propagation and detects unsafe recomposition. |
| **Context Governor** | Enforces token budgets. Preserves critical constraints. Prevents context saturation & rot. |
| **Audit Ledger** | Full execution trace. Replayable timelines. Compliance-ready evidence. |
| **Anomaly Detector** | Behavioral heuristics for rate-limit bursts and repetitive suspicious patterns. Auto-revokes compromised agents. |

---

## Project Structure

```
AVARA/
├── src/
│   ├── api/
│   │   ├── server.py              # FastAPI REST endpoints
│   │   └── framework_adapter.py   # Generic agent framework adapter
│   ├── core/
│   │   ├── iam_service.py         # Agent Identity & Access Management
│   │   └── audit_ledger.py        # Immutable audit logging
│   ├── guards/
│   │   ├── tool_guard.py          # Tool registration & permission enforcement
│   │   ├── circuit_breaker.py     # Excessive-agency halt & approval
│   │   ├── intent_validator.py    # Semantic drift detection
│   │   ├── rag_firewall.py        # RAG provenance & instruction scanning
│   │   ├── multi_agent_monitor.py # Cross-agent safety monitoring
│   │   ├── context_governor.py    # Token budget & safety anchoring
│   │   └── anomaly_detector.py    # Behavioral anomaly detection
│   ├── db/
│   │   └── persistent_store.py    # SQLite persistence layer
│   └── integrations/
│       └── langchain_adapter.py   # LangChain callback handler
├── avara_cli.py                   # Interactive CLI management tool
├── Dockerfile                     # Container image
├── docker-compose.yml             # Docker Compose config
└── requirements.txt               # Python dependencies
```

---

## Quick Start

### 1. Run with Docker (recommended)

```bash
docker compose up -d avara-api
docker compose logs -f avara-api
```

### 2. Run Locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn src.api.server:app --host 0.0.0.0 --port 8000
```

---

## AVARA CLI

The CLI supports both **direct commands** and a fully **interactive REPL mode**.

### Direct Commands

```bash
./avara_cli.py demo                                  # Run guided tour of all guards
./avara_cli.py status                                # Check server health
./avara_cli.py provision prod_agent "Marketing Bot"  # Create an identity
./avara_cli.py pending                               # List halted actions
./avara_cli.py approve <action_id>                   # Approve halted action
./avara_cli.py deny <action_id>                      # Deny halted action
./avara_cli.py revoke <agent_id>                     # Kill a rogue agent
./avara_cli.py logs                                  # View streaming audit log
```

### Interactive Mode

```bash
./avara_cli.py
# Launches the AVARA shell — type commands interactively
```

```
avara> status
  ✔  AVARA Authority is ONLINE

avara> provision prod_agent "My Bot" --scopes execute:read_file
  ✔  Identity provisioned
  Agent ID : agt_d67298cf

avara> pending
  No pending approvals. All clear.

avara> logs
  [2026-02-27 20:00:01] IAM_PROVISION  agt_d67298cf  ...
  [2026-02-27 20:00:03] ACTION_ALLOW   agt_d67298cf  ...

avara> exit
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/iam/provision` | Provision ephemeral agent identity |
| `DELETE` | `/iam/revoke/{agent_id}` | Revoke an agent identity |
| `POST` | `/guard/validate_action` | Main interceptor — validates intent, permissions, risk |
| `POST` | `/guard/prepare_context` | Context governor — enforces token budget |
| `POST` | `/guard/approvals/{id}/approve` | Webhook callback — approve halted action |
| `POST` | `/guard/approvals/{id}/deny` | Webhook callback — deny halted action |
| `GET` | `/guard/approvals/{id}/status` | Poll approval status |
| `GET` | `/health` | Server health check |

---

## Framework Integration (LangChain)

Wrap any LangChain agent with AVARA protection in 3 lines:

```python
from src.integrations.langchain_adapter import AVARALangChainCallback

avara_guard = AVARALangChainCallback(
    agent_id="agt_abc123",
    task_intent="Summarize financial documents"
)

agent = initialize_agent(
    tools, llm, agent="zero-shot-react-description",
    callbacks=[avara_guard]  # AVARA intercepts all tool calls
)
```

---

## Design Philosophy

1. **Runtime > Training** — Security is enforced at execution time, not training time
2. **Agents Are Actors** — Every agent has identity, permissions, and accountability
3. **Assume Compromise** — Documents, tools, agents, and outputs may all be hostile
4. **Explicit Over Implicit** — Registration, permissions, approvals, and audit trails are all explicit
5. **No Silent Side Effects** — Every mutation is observable, logged, and gateable

---

## Threat Model

AVARA defends against:

- Indirect prompt injection
- Excessive agent autonomy
- RAG-based permission bypass
- MCP / tool supply-chain attacks
- Autonomous data exfiltration
- Zero-click exploitation
- Multi-agent unsafe recomposition
- Context manipulation & rot
- Non-human identity abuse

---

## Validation Criteria

AVARA is correctly implemented when:

- No agent can act anonymously
- No destructive action occurs without approval
- No tool executes without registration
- No RAG document bypasses ACLs
- Every incident is replayable
- Every decision is attributable

---

> **AVARA does not make agents smarter. AVARA makes agents accountable.**
