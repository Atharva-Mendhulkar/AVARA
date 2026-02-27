from enum import Enum, auto
from dataclasses import dataclass
from typing import Dict, Any

class ValidationDecision(Enum):
    ALLOW = auto()
    REQUIRE_APPROVAL = auto()
    BLOCK = auto()

@dataclass
class AgentState:
    current_task: str
    proposed_action: str
    target_resource: str
    action_args: Dict[str, Any]

class IntentValidator:
    """
    Executes Intent Validation Engine rules:
    - Compares user intent (original task) vs agent action
    - Detects semantic drift
    - Blocks instruction hijacking
    - Stateless per action
    """
    def __init__(self):
        # Stub logic for semantic drift and instruction hijacking detection
        pass
        
    def _detect_drift(self, task: str, action: str) -> float:
        """
        Mock semantic drift detection.
        Returns a drift score from 0.0 (aligned) to 1.0 (hijacked/drifted).
        """
        # A real implementation would use an LLM or embedding distance here.
        # We mock a drift if the agent tries to send an email when asked to parse a file.
        if "analyze" in task.lower() and "email" in action.lower():
            return 0.9  
        
        # Catch our Interactive Demo severe drift scenario:
        if "summarize" in task.lower() and "delete" in action.lower():
            return 0.9
            
        return 0.1
        
    def validate_action(self, state: AgentState) -> ValidationDecision:
        """
        Validates the proposed action against the declared task intent.
        """
        drift_score = self._detect_drift(state.current_task, state.proposed_action)
        
        if drift_score > 0.8:
            print(f"INTENT VALIDATOR [BLOCK]: Severe semantic drift detected!")
            print(f"  Task:   {state.current_task}")
            print(f"  Action: {state.proposed_action} on {state.target_resource}")
            return ValidationDecision.BLOCK
            
        elif drift_score > 0.5:
            print(f"INTENT VALIDATOR [REQUIRE_APPROVAL]: Questionable alignment.")
            return ValidationDecision.REQUIRE_APPROVAL
            
        print(f"INTENT VALIDATOR [ALLOW]: Action aligned with task.")
        return ValidationDecision.ALLOW
