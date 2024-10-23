import logging
from falkordb import Graph
from typing import Optional
from graphrag_sdk.steps.Step import Step
from graphrag_sdk.ontology import Ontology
from graphrag_sdk.models import (
    GenerativeModelChatSession,
)
from graphrag_sdk.fixtures.prompts import (
    CYPHER_GEN_SYSTEM,
    CYPHER_GEN_PROMPT,
    CYPHER_GEN_PROMPT_WITH_ERROR,
    CYPHER_GEN_PROMPT_WITH_HISTORY,
)
from graphrag_sdk.helpers import (
    extract_cypher,
    validate_cypher,
    stringify_falkordb_response,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GraphQueryGenerationStep(Step):
    """
    Graph Query Step
    """

    def __init__(
        self,
        graph: Graph,
        ontology: Ontology,
        chat_session: GenerativeModelChatSession,
        config: dict = None,
        last_answer: str = None,
    ) -> None:
        self.ontology = ontology
        self.config = config or {}
        self.graph = graph
        self.chat_session = chat_session
        self.last_answer = last_answer

    def run(self, question: str, retries: int = 5):
        """
        Run the step to generate and validate a Cypher query.

        Args:
            question (str): The question being asked to generate the query.
            retries (int): Number of retries allowed in case of errors.

        Returns:
            tuple[Optional[str], Optional[str]]: The context and the generated Cypher query.
        """
        error = False

        cypher = ""
        while error is not None and retries > 0:
            try:
                cypher_prompt = (
                    (CYPHER_GEN_PROMPT.format(question=question) 
                    if self.last_answer is None
                    else CYPHER_GEN_PROMPT_WITH_HISTORY.format(question=question, last_answer=self.last_answer))
                    if error is False
                    else CYPHER_GEN_PROMPT_WITH_ERROR.format(
                        question=question, error=error
                    )
                )
                logger.debug(f"Cypher Prompt: {cypher_prompt}")
                cypher_statement_response = self.chat_session.send_message(
                    cypher_prompt,
                )
                logger.debug(f"Cypher Statement Response: {cypher_statement_response}")
                cypher = extract_cypher(cypher_statement_response.text)
                logger.debug(f"Cypher: {cypher}")

                if not cypher or len(cypher) == 0:
                    return (None, None)

                validation_errors = validate_cypher(cypher, self.ontology)
                if validation_errors is not None:
                    raise Exception("\n".join(validation_errors))

                if cypher is not None:
                    result_set = self.graph.query(cypher).result_set
                    context = stringify_falkordb_response(result_set)
                    logger.debug(f"Context: {context}")
                    logger.debug(f"Context size: {len(result_set)}")
                    logger.debug(f"Context characters: {len(str(context))}")

                return (context, cypher)
            except Exception as e:
                logger.debug(f"Error: {e}")
                error = e
                retries -= 1

        raise Exception("Failed to generate Cypher query: " + str(error))
