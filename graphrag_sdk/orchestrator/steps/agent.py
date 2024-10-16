import logging
from typing import Optional
from graphrag_sdk.agents.agent import AgentResponseCode
from graphrag_sdk.orchestrator.step_result import StepResult
from graphrag_sdk.orchestrator.step import PlanStep, StepBlockType
from graphrag_sdk.orchestrator.orchestrator_runner import OrchestratorRunner

logger = logging.getLogger(__name__)


class AgentStepResult(StepResult):
    """
    Represents the result of executing an agent step.

    Attributes:
        response_code (AgentResponseCode): The response code from the agent.
        payload (dict): The payload containing the result data.
    """

    def __init__(self, response_code: AgentResponseCode, payload: dict):
        self.response_code = response_code
        self.payload = payload

    def to_json(self) -> dict:
        """
        Convert the agent step result to a JSON-serializable dictionary.

        Returns:
            dict: A dictionary representation of the agent step result.
        """
        return {
            "response_code": self.response_code,
            "payload": self.payload,
        }

    @staticmethod
    def from_json(json: dict) -> "AgentStepResult":
        """
        Create an AgentStepResult instance from a JSON dictionary.

        Args:
            json (dict): The input JSON dictionary.

        Returns:
            AgentStepResult: An instance of AgentStepResult.
        """
        return AgentStepResult(
            AgentResponseCode.from_str(json["response_code"]),
            json["payload"],
        )

    def __str__(self) -> str:
        return f"AgentStepResult(response_code={self.response_code}, payload={self.payload})"

    def __repr__(self) -> str:
        return str(self)

    @property
    def output(self) -> str:
        return self.payload.get("output", str(self))


class AgentProperties:
    """
    Represents the properties for an agent step.

    Attributes:
        agent_id (str): The identifier for the agent.
        session_id (Optional[str]): The session identifier.
        payload (Optional[dict]): Additional payload data for the agent.
    """

    def __init__(self, agent_id: str, session_id: Optional[str] = None, payload: Optional[dict] = None):
        self.agent_id = agent_id
        self.session_id = session_id
        self.payload = payload

    @staticmethod
    def from_json(json: dict) -> "AgentProperties":
        """
        Create AgentProperties from a JSON dictionary.

        Args:
            json (dict): The input JSON dictionary.

        Returns:
            AgentProperties: An instance of AgentProperties.
        """
        return AgentProperties(
            json["agent_id"],
            json.get("session_id", None),
            json.get("payload", None),
        )

    def to_json(self) -> dict:
        """
        Convert the agent properties to a JSON-serializable dictionary.

        Returns:
            dict: A dictionary representation of the agent properties.
        """
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "payload": self.payload,
        }

    def __str__(self) -> str:
        return f"AgentProperties(agent_id={self.agent_id}, session_id={self.session_id}, payload={self.payload})"

    def __repr__(self) -> str:
        return str(self)


class AgentStep(PlanStep):
    """
    Represents a step that interacts with an agent.

    Attributes:
        id (str): The identifier for the step.
        properties (AgentProperties): The properties of the agent step.
    """
    
    def __init__(self, id: str, properties: AgentProperties):
        self._id = id
        self._properties = properties

    @property
    def id(self) -> str:
        return self._id

    @property
    def block(self) -> StepBlockType:
        return StepBlockType.AGENT

    @property
    def properties(self) -> AgentProperties:
        return self._properties

    def to_json(self) -> dict:
        """
        Convert the agent step to a JSON-serializable dictionary.

        Returns:
            dict: A dictionary representation of the agent step.
        """
        return {
            "id": self.id,
            "block": self.block,
            "properties": self.properties.to_json(),
        }

    @staticmethod
    def from_json(json: dict) -> "AgentStep":
        """
        Create an AgentStep from a JSON dictionary.

        Args:
            json (dict): The input JSON dictionary.

        Returns:
            AgentStep: An instance of AgentStep.
        """
        return AgentStep(json["id"], AgentProperties.from_json(json["properties"]))

    def __str__(self) -> str:
        return f"AgentStep(id={self.id}, properties={self.properties})"

    def __repr__(self) -> str:
        return str(self)

    def run(
        self,
        runner: "OrchestratorRunner",
        config: Optional[dict] = None,
    ) -> AgentStepResult:
        """
        Run the agent step, executing the agent with the provided properties.

        Args:
            runner (OrchestratorRunner): The orchestrator runner instance.
            config (Optional[dict]): Configuration options. Defaults to None.

        Returns:
            AgentStepResult: The result of the agent step execution.
        """
        logger.info(f"Running agent {self.properties.agent_id}, step: {self.id}, payload: {self.properties.payload}")
        session = (
            runner.get_session(self.properties.session_id)
            if self.properties.session_id
            else None
        )
        agent = runner.get_agent(self.properties.agent_id)
        if agent is None:
            raise ValueError(f"Agent with id {self.properties.agent_id} not found")

        (response, chat_session) = agent.run(self.properties.payload, session)
        runner.set_session(self.properties.session_id, chat_session)
        logger.debug(f"Agent response: {response}")
        return AgentStepResult(AgentResponseCode.AGENT_RESPONSE, {"output": response})
