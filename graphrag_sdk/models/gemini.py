import os
from typing import Optional
from google.generativeai import (
    GenerativeModel as GoogleGenerativeModel,
    GenerationConfig as GoogleGenerationConfig,
    configure,
    protos,
    types,)
from .model import (
    OutputMethod,
    GenerativeModel,
    GenerativeModelConfig,
    GenerationResponse,
    FinishReason,
    GenerativeModelChatSession,
)


class GeminiGenerativeModel(GenerativeModel):
    """
    A generative model that interfaces with GoogleAI API for chat completions.
    """
    
    _model: GoogleGenerativeModel = None

    def __init__(
        self,
        model_name: str,
        generation_config: Optional[GoogleGenerationConfig] = None,
        system_instruction: Optional[str] = None,
    ):
        """
        Initialize the GoogleGenerativeModel with required parameters.
        Args:
            model_name (str): Name of the GoogleAI model.
            generation_config (Optional[GoogleGenerationConfig]): Configuration settings for generation.
            system_instruction (Optional[str]): System-level instruction for the model.
        """
        self._model_name = model_name
        self._generation_config = generation_config or GenerativeModelConfig()
        self._system_instruction = system_instruction
        configure(api_key=os.environ["GOOGLE_API_KEY"])

    def start_chat(self, system_instruction: Optional[str] = None) -> GenerativeModelChatSession:
        """
        Start a new chat session.
        
        Args:
            system_instruction (Optional[str]): Optional system instruction to guide the chat session.
            
        Returns:
            GeminiChatSession: A new instance of the chat session.
        """
        self._model = GoogleGenerativeModel(
                self._model_name,
                generation_config=(
                    GoogleGenerationConfig(
                        temperature=self._generation_config.temperature,
                        top_p=self._generation_config.top_p,
                        top_k=self._generation_config.top_k,
                        max_output_tokens=self._generation_config.max_tokens,
                        stop_sequences=self._generation_config.stop,
                    )
                    if self._generation_config is not None
                    else None
                ),
                system_instruction=system_instruction,
            )
        
        return GeminiChatSession(self)
    
    def parse_generate_content_response(
        self, response: types.generation_types.GenerateContentResponse
    ) -> GenerationResponse:
        """
        Parse the model's response and extract content for the user.
        Args:
            response (any): The raw response from the model.
        Returns:
            GenerationResponse: Parsed response containing the generated text and finish reason.
        """
        return GenerationResponse(
            text=response.text,
            finish_reason=(
                FinishReason.MAX_TOKENS
                if response.candidates[0].finish_reason
                == protos.Candidate.FinishReason.MAX_TOKENS
                else (
                    FinishReason.STOP
                    if response.candidates[0].finish_reason == protos.Candidate.FinishReason.STOP
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
            "model_name": self._model_name,
            "generation_config": self._generation_config.to_json(),
            "system_instruction": self._system_instruction,
        }

    @staticmethod
    def from_json(json: dict) -> "GenerativeModel":
        """
        Deserialize a JSON object to create an instance of GeminiGenerativeModel.
        Args:
            json (dict): The serialized JSON data.
        Returns:
            GenerativeModel: A new instance of the model.
        """
        return GeminiGenerativeModel(
            model_name=json["model_name"],
            generation_config=GenerativeModelConfig.from_json(
                json["generation_config"]
            ),
            system_instruction=json["system_instruction"],
        )


class GeminiChatSession(GenerativeModelChatSession):
    """
    A chat session for interacting with the GoogleAI model, maintaining conversation history.
    """
    
    def __init__(self, model: GeminiGenerativeModel):
        """
        Initialize the chat session and set up the conversation history.
        
        Args:
            model (GeminiGenerativeModel): The model instance for the session.
        """
        
        self._model = model
        self._chat_session = self._model._model.start_chat()

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
        response = self._chat_session.send_message(message, generation_config=generation_config)
        return self._model.parse_generate_content_response(response)
    
    def _adjust_generation_config(self, output_method: OutputMethod) -> dict:
        """
        Adjust the generation configuration based on the output method.
        
        Args:
            output_method (OutputMethod): The desired output method (e.g., default or JSON).
            
        Returns:
            dict: The configuration settings for generation.
        """
        if output_method == OutputMethod.JSON:
            return {
                "response_mime_type": "application/json",
                "temperature": 0
            }
            
        config = self._model._generation_config.to_json()
        
        # Convert OpenAI-style config keys to GoogleAI-style keys
        config["max_output_tokens"] = config.pop("max_tokens")
        config["response_mime_type"] = config.pop("response_format")
        config["stop_sequences"] = config.pop("stop")
        return config
    
    def delete_last_message(self):
        """
        Deletes the last message exchange (user message and assistant response) from the chat history.
        Preserves the system message if present.
        
        Example:
            Before:
            [
                {"role": "user", "content": "User message"},
                {"role": "assistant", "content": "Assistant response"},
            ]
            After:
            []

        Note: Does nothing if the chat history is empty or contains only a system message.
        """
        if len(self._chat_session.history) >= 2:
            self._chat_session.history.pop()
            self._chat_session.history.pop()
        else:
            self._chat_session.history = []

