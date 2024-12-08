import os
import logging
from ollama import Client
from typing import Optional
from litellm import completion
from .model import (
    OutputMethod,
    GenerativeModel,
    GenerativeModelConfig,
    GenerationResponse,
    FinishReason,
    GenerativeModelChatSession,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) 

class LiteModel(GenerativeModel):
    """
    A generative model that interfaces with the LiteLLM for chat completions.
    """

    def __init__(
        self,
        model_name: str,
        generation_config: Optional[GenerativeModelConfig] = None,
        system_instruction: Optional[str] = None,
    ):
        """
        Initialize the LiteModel with the required parameters.

        Args:
            model_name (str): The name and the provider for the LiteLLM client.
            generation_config (Optional[GenerativeModelConfig]): Configuration settings for generation.
            system_instruction (Optional[str]): Instruction to guide the model.
        """

        self.model = model_name
        if "/" in model_name:
            self.provider = model_name.split("/")[0]
            self.model_name = model_name.split("/")[1]
        else:
            self.provider = "openai"
            self.model_name = model_name
        
        self.credentials_validation()
        self.generation_config = generation_config or GenerativeModelConfig()
        self.system_instruction = system_instruction
        
    def credentials_validation(self) -> None:
        """
        Validate the credentials for the model.

        Returns:
            bool: True if the credentials are valid, False otherwise.
        """
        if self.provider == "openai":
            if not os.getenv("OPENAI_API_KEY"):
                raise ValueError("Missing OpenAI API key in the environment.")
               
        elif self.provider == "azure":
            if not os.getenv("AZURE_API_KEY") or not os.getenv("AZURE_API_BASE") or not os.getenv("AZURE_API_VERSION"):
                raise ValueError("Missing Azure-OpenAI credentials in the environment. See the Github Readme for more information.")
        
        elif self.provider == "gemini":
            if not os.getenv("GEMINI_API_KEY"):
                raise ValueError("Missing Gemini API key in the environment.")
        
        elif self.provider == "ollama":
            self.ollama_client = Client()
            self.check_and_pull_model()
            
    def check_and_pull_model(self) -> None:
        """
        Checks if the specified model is available locally, and pulls it if not.

        Logs:
            - Info: If the model is already available or after successfully pulling the model.
            - Error: If there is a failure in pulling the model.

        Raises:
            Exception: If there is an error during the model pull process.
        """
        # Get the list of available models
        response = self.ollama_client.list()  # This returns a dictionary
        available_models = [model['name'] for model in response['models']]  # Extract model names

        # Check if the model is already pulled
        if self.model_name in available_models:
            logger.info(f"The model '{self.model_name}' is already available.")
        else:
            logger.info(f"Pulling the model '{self.model_name}'...")
            try:
                self.ollama_client.pull(self.model_name)  # Pull the model
                logger.info(f"Model '{self.model_name}' pulled successfully.")
            except Exception as e:
                logger.error(f"Failed to pull the model '{self.model_name}': {e}")

    def with_system_instruction(self, system_instruction: str) -> "GenerativeModel":
        """
        Set or update the system instruction for new model instance.

        Args:
            system_instruction (str): Instruction for guiding the model's behavior.
        
        Returns:
            GenerativeModel: The updated model instance.
        """
        self.system_instruction = system_instruction
        return self

    def start_chat(self, args: Optional[dict] = None) -> GenerativeModelChatSession:
        """
        Start a new chat session.

        Args:
            args (Optional[dict]): Additional arguments for the chat session.

        Returns:
            GenerativeModelChatSession: A new instance of the chat session.
        """
        return LiteModelChatSession(self, args)

    def parse_generate_content_response(self, response: any) -> GenerationResponse:
        """
        Parse the model's response and extract content for the user.

        Args:
            response (any): The raw response from the model.

        Returns:
            GenerationResponse: Parsed response containing the generated text.
        """
        return GenerationResponse(
            text=response.choices[0].message.content,
            finish_reason=(
                FinishReason.STOP
                if response.choices[0].finish_reason == "stop"
                else (
                    FinishReason.MAX_TOKENS
                    if response.choices[0].finish_reason == "length"
                    else FinishReason.OTHER
                )
            ),
        )

    def to_json(self) -> dict:
        """
        Serialize the model's configuration and state to JSON format.

        Returns:
            dict: The serialized JSON data.
        """
        return {
            "model_name": self.model_name,
            "generation_config": self.generation_config.to_json(),
            "system_instruction": self.system_instruction,
        }

    @staticmethod
    def from_json(json: dict) -> "GenerativeModel":
        """
        Deserialize a JSON object to create an instance of LiteLLMGenerativeModel.

        Args:
            json (dict): The serialized JSON data.

        Returns:
            GenerativeModel: A new instance of the model.
        """
        return LiteModel(
            json["model_name"],
            generation_config=GenerativeModelConfig.from_json(
                json["generation_config"]
            ),
            system_instruction=json["system_instruction"],
        )


class LiteModelChatSession(GenerativeModelChatSession):
    """
    A chat session for interacting with the LiteLLM model, maintaining conversation history.
    """

    def __init__(self, model: LiteModel, args: Optional[dict] = None):
        """
        Initialize the chat session and set up the conversation history.

        Args:
            model (LiteLLMGenerativeModel): The model instance for the session.
            args (Optional[dict]): Additional arguments for customization.
        """
        self._model = model
        self._args = args
        self._chat_history = (
            [{"role": "system", "content": self._model.system_instruction}]
            if self._model.system_instruction is not None
            else []
        )
        
    def get_chat_history(self) -> list[dict]:
        """
        Retrieve the conversation history for the current chat session.

        Returns:
            list[dict]: The chat session's conversation history.
        """
        return self._chat_history.copy()

    def send_message(self, message: str, output_method: OutputMethod = OutputMethod.DEFAULT) -> GenerationResponse:
        """
        Send a message in the chat session and receive the model's response.

        Args:
            message (str): The message to send.
            output_method (OutputMethod): Format for the model's output.

        Returns:
            GenerationResponse: The generated response.
        """
        generation_config = self._adjust_generation_config(output_method)
        self._chat_history.append({"role": "user", "content": message})
        response = completion(
            model=self._model.model,
            messages=self._chat_history,
            **generation_config
            )
        content = self._model.parse_generate_content_response(response)
        self._chat_history.append({"role": "assistant", "content": content.text})
        return content
    
    def _adjust_generation_config(self, output_method: OutputMethod):
        """
        Adjust the generation configuration based on the specified output method.

        Args:
            output_method (OutputMethod): The desired output method (e.g., default or JSON).

        Returns:
            dict: The adjusted configuration settings for generation.
        """
        config = self._model.generation_config.to_json()
        if output_method == OutputMethod.JSON:
            config['temperature'] = 0
            config['response_format'] = { "type": "json_object" }
        
        return config
    
    def delete_last_message(self):
        """
        Deletes the last message exchange (user message and assistant response) from the chat history.
        Preserves the system message if present.
        
        Example:
            Before:
            [
                {"role": "system", "content": "System message"},
                {"role": "user", "content": "User message"},
                {"role": "assistant", "content": "Assistant response"},
            ]
            After:
            [
                {"role": "system", "content": "System message"},
            ]

        Note: Does nothing if the chat history is empty or contains only a system message.
        """
        # Keep at least the system message if present
        min_length = 1 if self._model.system_instruction else 0
        if len(self._chat_history) - 2 >= min_length:
            self._chat_history.pop()
            self._chat_history.pop()
        else:
            # Reset to initial state with just system message if present
            self._chat_history = (
            [{"role": "system", "content": self._model.system_instruction}]
            if self._model.system_instruction is not None
            else []
        )
