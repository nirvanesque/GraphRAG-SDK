import logging
from typing import Optional
from graphrag_sdk.agents import Agent
from .execution_plan import ExecutionPlan
from graphrag_sdk.helpers import extract_json
from .step import StepResult, PlanStep, StepBlockType
from graphrag_sdk.models import GenerativeModelChatSession
from graphrag_sdk.fixtures.prompts import ORCHESTRATOR_DECISION_PROMPT
from .orchestrator_decision import OrchestratorDecision, OrchestratorDecisionCode


logger = logging.getLogger(__name__)

class OrchestratorResult(StepResult):
    """
    Represents the result of an orchestrator execution step.
    """

    def __init__(self, output: str):
        """
        Initialize a new OrchestratorResult object.
        
        Args:
        _output (str): The output generated by the orchestrator.
        """
        self._output = output

    def to_json(self) -> dict:
        """
        Convert the orchestrator result to a JSON-serializable dictionary.
        
        Returns:
            dict: A dictionary representation of the orchestrator result.
        """
        return {
            "output": self._output,
        }

    @staticmethod
    def from_json(json: dict) -> "OrchestratorResult":
        return OrchestratorResult(
            json["output"],
        )

    def __str__(self) -> str:
        return f"OrchestratorResult(output={self._output})"

    def __repr__(self) -> str:
        return str(self)

    @property
    def output(self) -> str:
        """
        Get the output of the orchestrator result.
        
        Returns:
            str: The output generated by the orchestrator.
        """
        return self._output


class OrchestratorRunner:
    """
    Manages the execution of an orchestrator plan, coordinating the involved agents.
    """
    
    _runner_log: list[tuple[PlanStep, StepResult]] = []
    _agent_sessions: dict[str, GenerativeModelChatSession] = {}

    def __init__(
        self,
        chat: GenerativeModelChatSession,
        agents: list[Agent],
        plan: ExecutionPlan,
        user_question: Optional[str] = None,
        config: Optional[dict] = None,
    ):
        """
        Initialize a new OrchestratorRunner object.
        
        Args:
            chat (GenerativeModelChatSession): The chat session used for communication with the model.
            agents (list[Agent]): List of registered agents for executing tasks.
            plan (ExecutionPlan): The execution plan that dictates the steps to be executed.
            user_question (str): The user's original question.
            config (dict): Configuration settings for the orchestrator.
        """
        self._chat = chat
        self._agents = agents
        self._plan = plan
        self._user_question = user_question
        self._config = config or {"parallel_max_workers": 16}
        self._runner_log = []
        self._agent_sessions = {}

    @property
    def plan(self) -> ExecutionPlan:
        """
        Get the execution plan.
        
        Returns:
            ExecutionPlan: The current execution plan.
        """
        return self._plan

    @property
    def chat(self) -> GenerativeModelChatSession:
        """
        Get the chat session.
        
        Returns:
            GenerativeModelChatSession: The current chat session.
        """
        return self._chat

    @property
    def runner_log(self) -> list[tuple[PlanStep, StepResult]]:
        """
        Get the log of executed steps and their results.
        
        Returns:
            list[tuple[PlanStep, StepResult]]: The log of steps executed.
        """
        return self._runner_log

    @property
    def user_question(self) -> str:
        """
        Get the user's original question.
        
        Returns:
            str: The user's question.
        """
        return self._user_question

    def get_agent(self, agent_id: str) -> Agent:
        """
        Retrieve an agent by its ID.
        
        Args:
            agent_id (str): The ID of the agent to retrieve.
            
        Returns:
            Agent: The agent corresponding to the provided ID.
        """
        return next(agent for agent in self._agents if agent.agent_id == agent_id)

    def get_session(self, session_id: str) -> Optional[GenerativeModelChatSession]:
        """
        Retrieve the chat session for a specific agent.
        
        Args:
            session_id (str): The ID of the session to retrieve.
            
        Returns:
            Optional[GenerativeModelChatSession]: The corresponding session or None if not found.
        """
        return self._agent_sessions.get(session_id, None)

    def set_session(self, session_id: str, session: GenerativeModelChatSession):
        """
        Set the chat session for a specific agent.
        
        Args:
            session_id (str): The ID of the session to set.
            session (GenerativeModelChatSession): The session to associate with the agent.
        """
        
        self._agent_sessions[session_id] = session

    def get_user_input(self, question: str) -> str:
        """
        Get user input based on a prompt.
        
        Args:
            question (str): The prompt to display to the user.
            
        Returns:
            str: The user's input.
        """
        
        return input(question)

    def run(self) -> OrchestratorResult:
        """
        Execute the orchestrator plan and return the result.
        
        Returns:
            OrchestratorResult: The result of the orchestrator execution.
            
        Raises:
            ValueError: If the execution plan is empty.
        """

        if not self._plan.steps:
            raise ValueError("Execution plan contains no steps to execute.")

        first_step = self._plan.steps[0]

        first_step_result = first_step.run(self)

        self._runner_log.append((first_step, first_step_result))

        loop_response = self._run_loop(self._plan.steps[1:])

        logger.info(f"Execution log: {self._runner_log}")
        logger.info(f"Execution result: {loop_response}")

        return loop_response

    def _run_loop(self, steps: list[PlanStep]) -> StepResult:
        """
        Run a loop through the steps of the execution plan and handle decisions.
        
        Args:
            steps (list[PlanStep]): The remaining steps to execute.
            
        Returns:
            StepResult: The result of the execution.
        """
        decision = self._get_orchestrator_decision(
            steps[0] if len(steps) > 0 else None,
        )

        if decision.code == OrchestratorDecisionCode.END:
            return self._handle_end_decision()
        elif decision.code == OrchestratorDecisionCode.CONTINUE:
            return self._handle_continue_decision(steps)
        elif decision.code == OrchestratorDecisionCode.UPDATE_STEP:
            return self._handle_update_step_decision(decision.new_step)
        else:
            raise ValueError(f"Unhandled OrchestratorDecisionCode: {decision.code}")

    def _handle_end_decision(self) -> StepResult:
        """
        Handle the decision to end the orchestration.
        
        Returns:
            StepResult: The result of the orchestration upon ending.
        """
        last_step = self._runner_log[-1][0] if len(self._runner_log) > 0 else None
        if last_step is None:
            return OrchestratorResult("Execution plan contains no steps to execute.")
        
        if last_step.block != StepBlockType.SUMMARY:
            return self._call_summary_step()
        last_result = self._runner_log[-1][1] if len(self._runner_log) > 0 else None

        return (
            OrchestratorResult(last_result.output)
            if last_result
            else OrchestratorResult("No steps to run")
        )

    def _handle_continue_decision(self, steps: list[PlanStep]) -> StepResult:
        """
        Handle the decision to continue with the next step in the execution.
        
        Args:
            steps (list[PlanStep]): The remaining steps to execute.
            
        Returns:
            StepResult: The result of the next step execution.
        """
        if len(steps) == 0:
            return self._handle_end_decision()

        next_step = steps[0]
        next_step_result = next_step.run(self)
        self._runner_log.append((next_step, next_step_result))
        return self._run_loop(steps[1:])

    def _handle_update_step_decision(self, new_step: PlanStep) -> StepResult:
        """
        Handle the decision to update the current step.
        
        Args:
            new_step (PlanStep): The new step to execute.
            
        Returns:
            StepResult: The result of the new step execution.
        """
        next_step_result = new_step.run(self)
        self._runner_log.append((new_step, next_step_result))
        return self._run_loop([])

    def _call_summary_step(self):
        """
        Call the summary step at the end of the orchestration.
        
        Returns:
            StepResult: The result of the summary step execution.
        """
        return self._run_loop(
            [
                PlanStep.from_json(
                    {
                        "block": StepBlockType.SUMMARY,
                        "id": "summary",
                        "properties": {},
                    }
                )
            ]
        )

    def _get_orchestrator_decision(
        self,
        next_step: Optional[PlanStep] = None,
    ) -> OrchestratorDecision:
        """
        Get the orchestrator's decision based on the current step and context.
        
        Args:
            next_step (Optional[PlanStep]): The next step to evaluate for decision making.
            
        Returns:
            OrchestratorDecision: The decision made by the orchestrator.
        """

        response = self.chat.send_message(
            ORCHESTRATOR_DECISION_PROMPT.replace(
                "#LOG_HISTORY",
                str(self._runner_log),
            ).replace(
                "#NEXT_STEP",
                str(next_step),
            )
        )

        logger.debug(f"Orchestrator decision response: {response.text}")

        return OrchestratorDecision.from_json(extract_json(response.text))
