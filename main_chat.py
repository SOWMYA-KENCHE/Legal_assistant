
import os
from dotenv import load_dotenv
from autogen import AssistantAgent, UserProxyAgent
from tools import retrieve_legal_context
load_dotenv()
import google.generativeai as genai


# Configure Gemini with API key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
def gemini_generate(prompt: str, model="gemini-2.5-flash", temperature=0.3) -> str:
    """Wrapper to call Gemini like an OpenAI model."""
    try:
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"[Gemini Error: {e}]"

# Gemini LLM config (same structure as Ollama/OpenAI)
llm_config = {
    "config_list": [
        {
            "model": "gemini-2.5-flash",  # ✅ Safe tag that passes validation
            "api_type": "google",  # ✅ Safe tag that passes validation
            "api_key": os.getenv("GEMINI_API_KEY"),
            "custom_generate": gemini_generate,  # 👈 store our custom function
        }
    ],
    "temperature": 0.3
}



def is_termination_msg(msg):
    return msg.get("content") and "TERMINATE" in msg["content"]

# Define the assistant agent
legal_assistant = AssistantAgent(
    name="LegalAssistant",
    system_message=(
        "You are a helpful legal assistant that retrieves relevant clauses from legal documents.\n" \
        "Please give summarised responses to user queries based on the legal context retrieved.\n" \
        "After answering the user query, always respond with 'TERMINATE' to end the chat."
    ),
    llm_config = llm_config
)

# Define the user proxy agent
user = UserProxyAgent(
    name="User",
    llm_config=False,
    human_input_mode="NEVER",  # auto-execution
    is_termination_msg = is_termination_msg,
    code_execution_config={"use_docker": False}
)


# Register the tool with both agents
legal_assistant.register_for_llm(
    name="retrieve_legal_context",
    description="Retrieve relevant legal context from the indexed legal documents based on the query."
)(retrieve_legal_context)

user.register_for_execution(
    name="retrieve_legal_context"
)(retrieve_legal_context)

if __name__ == "__main__":# Initiate the conversation
    user.initiate_chat(
        legal_assistant,
        message="Can I have a pet in the apartment?"
    )
