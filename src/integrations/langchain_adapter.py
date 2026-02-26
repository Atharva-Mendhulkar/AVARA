from typing import Any, Dict, Optional, List
import requests
import logging

try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.agents import AgentAction
    from langchain_core.messages import BaseMessage
except ImportError:
    logging.warning("Langchain is not installed. AVARALangChainCallback overrides will be inactive.")
    BaseCallbackHandler = object # Dummy base to prevent import error
    AgentAction = Any
    BaseMessage = Any

class AVARALangChainCallback(BaseCallbackHandler):
    """
    A LangChain Callback Handler that intercepts tool execution and LLM interactions
    to securely funnel them through the AVARA control plane API.
    """
    def __init__(self, agent_id: str, task_intent: str, api_base_url: str = "http://127.0.0.1:8000"):
        self.agent_id = agent_id
        self.task_intent = task_intent
        self.api_base_url = api_base_url
        self.logger = logging.getLogger(__name__)

    def _post_avara(self, endpoint: str, payload: dict) -> dict:
        try:
            resp = requests.post(f"{self.api_base_url}{endpoint}", json=payload)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            # Re-raise as a standard Exception so LangChain agent loop can catch/handle it
            # without obscure requests library knowledge.
            raise PermissionError(f"AVARA Authority Blocked Action: {e.response.text}")

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> Any:
        """
        Intercepts right before a LangChain tool executes.
        """
        tool_name = serialized.get("name", "unknown_tool")
        
        # We attempt to infer risk based on typical LangChain tools 
        # (e.g. bash or python repl are high risk, calculators are low risk)
        risk_level = "HIGH" if tool_name.lower() in ["python_repl", "terminal", "bash", "requests"] else "MEDIUM"
        
        args = kwargs.get("inputs", {})
        if not args and input_str:
            args = {"input": input_str}

        payload = {
            "agent_id": self.agent_id,
            "task_intent": self.task_intent,
            "proposed_action": tool_name,
            "target_resource": "langchain_tool",
            "action_args": args,
            "risk_level": risk_level
        }
        
        self.logger.info(f"AVARA Intercept: Validating {tool_name} execution...")
        # Will raise PermissionError if AVARA blocks it, preventing execution.
        self._post_avara("/guard/validate_action", payload)
        self.logger.info(f"AVARA Intercept: Execution allowed.")

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[BaseMessage]], **kwargs: Any) -> Any:
        """
        Intercepts before sending prompt to LLM to enforce Context Governor limits.
        """
        if not messages or not messages[0]:
            return
            
        flat_messages = messages[0]
        # Very rough approximation for MVP adapter
        system_content = next((m.content for m in flat_messages if m.type == "system"), "")
        user_content = next((m.content for m in flat_messages if m.type == "human"), "")
        
        if not user_content:
            return
            
        payload = {
            "agent_id": self.agent_id,
            "dynamic_query": user_content,
            "system_prompt": system_content
        }
        
        self.logger.info(f"AVARA Intercept: Preparing constrained context...")
        # Will raise PermissionError if SATURATED
        res = self._post_avara("/guard/prepare_context", payload)
        
        # (Advanced behavior): In a real profound integration, we would mutate the `messages` list 
        # inline here to forcibly inject the Context Governor's `final_context_block`.
        # However, Langchain's base callback doesn't support mutating inputs natively, 
        # it requires a custom wrapping chain. So we use this just for validation.
        self.logger.info(f"AVARA Intercept: Context Budget {res.get('budget_used')} Tokens.")
