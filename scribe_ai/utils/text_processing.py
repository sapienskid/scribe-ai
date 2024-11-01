import logging
import json
import google.generativeai as genai
from .config import api_manager, api_parameters
import google.api_core.exceptions
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SafetySetting:
    category: str
    threshold: str

class APIConfigurationError(Exception):
    """Custom exception for API configuration errors."""
    pass

class SystemInstructionError(Exception):
    """Custom exception for system instruction related errors."""
    pass

def configure_api() -> None:
    """Configure the Gemini API with the current API key."""
    current_key = api_manager.get_current_key()
    try:
        genai.configure(api_key=current_key)
        logger.info(f"Configured API with key {current_key[:5]}...")
    except Exception as e:
        logger.error(f"Error configuring API with key {current_key[:5]}...: {str(e)}")
        raise APIConfigurationError(f"Failed to configure API: {str(e)}")

configure_api()

class GeminiAPI:
    DEFAULT_SAFETY_SETTINGS = [
        SafetySetting("HARM_CATEGORY_HARASSMENT", "BLOCK_ONLY_HIGH"),
        SafetySetting("HARM_CATEGORY_HATE_SPEECH", "BLOCK_ONLY_HIGH"),
        SafetySetting("HARM_CATEGORY_SEXUALLY_EXPLICIT", "BLOCK_ONLY_HIGH"),
        SafetySetting("HARM_CATEGORY_DANGEROUS_CONTENT", "BLOCK_ONLY_HIGH")
    ]

    def __init__(self, use_json: bool = False) -> None:
        """
        Initialize the GeminiAPI instance.
        
        Args:
            use_json (bool): Whether to return responses as JSON
        """
        self.generation_config = {
            "temperature": api_parameters["temperature"],
            "top_p": api_parameters["top_p"],
            "top_k": int(api_parameters["top_k"] * 100),
            "max_output_tokens": 8192,
            "response_mime_type": "application/json" if use_json else "text/plain",
        }
        
        self.safety_settings = [
            {"category": setting.category, "threshold": setting.threshold}
            for setting in self.DEFAULT_SAFETY_SETTINGS
        ]
        
        self.model = self._initialize_model()
        self.chat_session = None
        self.system_instruction: Optional[str] = None
        self.chat_history: List[Dict[str, str]] = []
        
        # Initialize chat session
        self.reset_chat()

    def _initialize_model(self) -> genai.GenerativeModel:
        """Initialize and return a new GenerativeModel instance."""
        return genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=self.generation_config,
            safety_settings=self.safety_settings
        )

    def _validate_system_instruction(self, instruction: str) -> None:
        """
        Validate the system instruction format and content.
        
        Args:
            instruction (str): The system instruction to validate
            
        Raises:
            SystemInstructionError: If the instruction is invalid
        """
        if not instruction or not instruction.strip():
            raise SystemInstructionError("System instruction cannot be empty")
        
        if len(instruction) > 2000:  # Arbitrary limit, adjust as needed
            raise SystemInstructionError("System instruction too long (max 2000 characters)")
        
        # Add any other validation rules as needed

    def set_system_instruction(self, instruction: str) -> None:
        """
        Set and validate the system instruction.
        
        Args:
            instruction (str): The system instruction to set
        """
        try:
            self._validate_system_instruction(instruction)
            logger.info(f"Setting system instruction: {instruction[:50]}...")
            self.system_instruction = instruction
            self.reset_chat()
        except SystemInstructionError as e:
            logger.error(f"Invalid system instruction: {str(e)}")
            raise

    def clear_system_instruction(self) -> None:
        """Clear the current system instruction and reset the chat."""
        logger.info("Clearing system instruction")
        self.system_instruction = None
        self.reset_chat()

    def get_system_instruction(self) -> Optional[str]:
        """Return the current system instruction."""
        return self.system_instruction

    def switch_and_reconfigure(self) -> None:
        """Switch to the next API key and reconfigure the model."""
        old_key = api_manager.get_current_key()
        api_manager.switch_key()
        new_key = api_manager.get_current_key()
        logger.info(f"Switched API key from {old_key[:5]}... to {new_key[:5]}...")
        
        try:
            configure_api()
            logger.info("Reconfiguring Gemini model with new API key")
            self.model = self._initialize_model()
            self.reset_chat()
            logger.info("Gemini model reconfigured successfully")
        except APIConfigurationError as e:
            logger.error(f"Failed to reconfigure with new key: {str(e)}")
            raise

    async def generate_content(self, prompt: str) -> Optional[Any]:
        """
        Generate content using the chat session.
        
        Args:
            prompt (str): The user prompt
            
        Returns:
            Optional[Any]: The generated content, either as text or JSON
        """
        try:
            formatted_prompt = f"Human: {prompt}"
            logger.info(f"Sending prompt to Gemini API: {formatted_prompt[:200]}...")
            
            response = self.chat_session.send_message(formatted_prompt)
            logger.info("Received response from Gemini API")
            
            # Store in chat history
            self.chat_history.append({
                "role": "user",
                "content": prompt
            })
            self.chat_history.append({
                "role": "assistant",
                "content": response.text
            })
            
            if self.generation_config["response_mime_type"] == "application/json":
                try:
                    return json.loads(response.text)
                except json.JSONDecodeError as json_error:
                    logger.error(f"JSON decode error: {str(json_error)}")
                    logger.error(f"Raw response: {response.text[:1000]}...")
                    return response.text
            return response.text
            
        except google.api_core.exceptions.ResourceExhausted:
            logger.error("API key exhausted. Switching to next key.")
            self.switch_and_reconfigure()
            return await self.generate_content(prompt)  # Retry with new key
        except Exception as e:
            logger.error(f"An error occurred while generating content: {str(e)}")
            return None

    def reset_chat(self) -> None:
        """Reset the chat session and initialize with system instruction if present."""
        logger.info("Resetting chat session")
        max_retries = len(api_manager.api_keys)
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries} to reset chat session")
                
                # Initialize new chat session
                self.chat_session = self.model.start_chat(history=[])
                self.chat_history = []  # Clear chat history
                
                # If system instruction exists, send it with proper formatting
                if self.system_instruction:
                    logger.info("Sending system instruction")
                    formatted_instruction = f"System: {self.system_instruction}"
                    response = self.chat_session.send_message(formatted_instruction)
                    
                    # Store system instruction in history
                    self.chat_history.append({
                        "role": "system",
                        "content": self.system_instruction
                    })
                    
                    logger.info(f"System instruction sent successfully. Response: {response.text[:100]}...")
                
                logger.info("Chat session reset successfully")
                return
                
            except google.api_core.exceptions.ResourceExhausted as e:
                logger.warning(f"ResourceExhausted error during reset (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    self.switch_and_reconfigure()
                else:
                    logger.error("All API keys exhausted. Unable to reset chat session.")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error during reset: {str(e)}")
                raise

    def update_safety_settings(self, new_settings: List[SafetySetting]) -> None:
        """
        Update the safety settings for the model.
        
        Args:
            new_settings (List[SafetySetting]): List of new safety settings
        """
        logger.info("Updating safety settings")
        self.safety_settings = [
            {"category": setting.category, "threshold": setting.threshold}
            for setting in new_settings
        ]
        
        self.model = self._initialize_model()
        self.reset_chat()

    def get_chat_history(self) -> List[Dict[str, str]]:
        """Return the current chat history."""
        return self.chat_history.copy()