import os
import tempfile
import shutil
import time
import json
import re
import sqlite3
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, JWTManager
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List, Tuple
import fitz
import requests
from flask import request, jsonify
from langchain_community.tools import DuckDuckGoSearchRun
import warnings
warnings.filterwarnings("ignore", message="PydanticSerializationUnexpectedValue")
from auth import (
    add_user, check_user,
    save_chat_message, load_chat_history,
    save_document_summary, load_document_summary
)
from fact_checker import fact_checker_agent
from rag_index_builder import build_index_from_pdf
from tools import retrieve_legal_context
from web_search_tool import search_web
from database import db_init
from indiankanoon_api_tool import search_indiankanoon_api
import autogen
from autogen import AssistantAgent, UserProxyAgent
from autogen import Agent

def custom_gemini_completion(agent: Agent, messages, **kwargs):
    """Force Autogen to use Gemini for all LLM replies."""
    try:
        prompt = messages[-1]["content"] if isinstance(messages, list) else str(messages)
        config = agent.llm_config["config_list"][0]
        generate_func = config.get("custom_generate")
        if callable(generate_func):
            return generate_func(prompt)
        return "[Error: Gemini generator missing]"
    except Exception as e:
        return f"[Gemini Patch Error: {e}]"

# 🧠 Patch the core LLM reply function
Agent._generate_reply = lambda self, messages, **kwargs: custom_gemini_completion(self, messages, **kwargs)
load_dotenv()
# --- Flask App Setup ---
app = Flask(__name__, static_folder=None)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super-secret-key-please-change")
jwt = JWTManager(app)
CORS(app, supports_credentials=True)

# --- LLM Configuration ---
# llm_config = {
#     "config_list": [
#         {
#             "model": "gpt-5-nano",     # or gpt-4o / gpt-4-turbo / gpt-3.5-turbo
#             "api_key": os.getenv("OPENAI_API_KEY"),
#             "api_type": "openai"
#         }
#     ],
#     "temperature": 0.3
# }
import google.generativeai as genai
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
import time

def gemini_generate(prompt: str, model="gemini-2.5-flash", temperature=0.3, retries=3) -> str:
    """Wrapper to call Gemini with retry logic."""
    for attempt in range(retries):
        try:
            model_instance = genai.GenerativeModel(model)
            response = model_instance.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            error_text = str(e)
            if "503" in error_text or "UNAVAILABLE" in error_text:
                print(f"[Gemini busy] Retrying... attempt {attempt + 1}/{retries}")
                time.sleep(3)  # wait before retrying
                continue
            return f"[Gemini Error: {e}]"
    return "[Gemini Error: Model temporarily unavailable. Please try again later.]"

llm_config = {
    "config_list": [
        {
            "model": "gemini-2.5-flash",
            "api_type": "google",  # ✅ Safe tag that passes validation
            "api_key": os.getenv("GEMINI_API_KEY"),
            "custom_generate": gemini_generate,  # 👈 store our custom function
        }
    ],
    "temperature": 0.3
}
def is_termination_msg(msg: Dict[str, Any]) -> bool:
    content = msg.get("content")
    return content is not None and "TERMINATE" in content
# 🧠 SUMMARIZER AGENT
def get_full_text_from_pdf(pdf_path: str) -> str:
    """Extracts full text from a PDF file."""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        max_chars = 20000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n... [Text truncated for summarization]"
        return text
    except Exception as e:
        print(f"Error reading PDF for summary: {e}")
        return ""


def run_summarizer_agent(full_text: str) -> str:
    """Runs the summarizer agent."""
    if not full_text:
        return "Could not summarize: No text provided or PDF was unreadable."

    summarizer_agent = AssistantAgent(
        name="SummarizerAgent",
        system_message=(
            "You are an expert legal summarizer. You will be given text from a legal document. "
            "Provide a concise, multi-paragraph summary of its key points."
            "and generate a structured summary and print it in json format with the following fields:\n"
            "case_title , court ,year ,key_issues,Arguments,Citations Present,judgement_summary,important_sections,Important Clauses,key_takeaways"
            "Do not add conversational fluff. End with TERMINATE."

        ),
        llm_config=llm_config,
    )

    user_proxy = UserProxyAgent(
        name="SummaryUserProxy",
        llm_config=False,
        human_input_mode="NEVER",
        is_termination_msg=is_termination_msg,
        code_execution_config={"use_docker": False}
    )

    try:
        chat_result = user_proxy.initiate_chat(summarizer_agent, message=full_text)
        history = getattr(chat_result, "chat_history", None)
        if history:
            for msg in reversed(history):
                if msg.get("name") == "SummarizerAgent":
                    content = msg.get("content", "").replace("TERMINATE", "").strip()
                    if content:
                        return content
        return "Failed to generate summary."
    except Exception as e:
        print(f"Error during summarization: {e}")
        return f"Failed to generate summary due to error: {e}"
# ⚖️ PRECEDENT FINDER AGENT
def format_precedent_results(results: list[dict]) -> str:
    """
    Converts precedent data (list of dicts) into formatted Markdown text.
    Example:
    [
      {"name": "Case 1", "court": "Supreme Court", "year": "2024", "url": "https://...", "confidence": 0.9}
    ]
    """
    if not results:
        return "No precedents found."

    formatted_lines = ["### ⚖️ Similar Precedents Found\n"]
    for i, r in enumerate(results, 1):
        name = r.get("name", "Unnamed Case")
        court = r.get("court", "Court Unknown")
        year = r.get("year", "Year N/A")
        url = r.get("url", "")
        conf = r.get("confidence", 0)

        formatted_lines.append(f"**{i}. {name}**  ")
        formatted_lines.append(f"📅 Year: {year}  ")
        formatted_lines.append(f"⚖️ Court: {court}  ")
        if url:
            formatted_lines.append(f"🔗 [Read Full Judgment]({url})  ")
        formatted_lines.append("")  # line break

    return "\n".join(formatted_lines)

def search_web_wrapper(query: str) -> str:
    """Wrapper around DuckDuckGoSearchRun.run() so it can be used by Autogen."""
    try:
        return search_web.run(query)
    except Exception as e:
        return f"Web search failed: {e}"
    
from google_scholar_tool import search_google_scholar_legal

def run_precedent_finder_agent(summary_text: str) -> str:
    """Runs an AI agent to find similar legal precedents from multiple sources."""
    if not summary_text:
        return "Could not find precedents: No summary text provided."

    from langchain_community.tools import DuckDuckGoSearchRun
    search_web = DuckDuckGoSearchRun()
    try:
        from google_scholar_tool import search_google_scholar_legal
    except ImportError:
        def search_google_scholar_legal(query: str, limit: int = 5) -> list[dict]:
            return "Google Scholar tool not available."

    precedent_finder = AssistantAgent(
        name="PrecedentFinderAgent",
        system_message=(
            "You are LexiLaw’s Precedent Finder.\n"
            "You analyze the summary of a legal document and find real-world case precedents.\n\n"
            "## STEPS:\n"
            "1️⃣ Identify 5–7 relevant legal issues or concepts.\n"
            "2️⃣ Use `search_indian_kanoon` to find Indian cases.\n"
            "3️⃣ If no results or tool error, automatically fallback to `search_google_scholar_legal`.\n"

            "Output should always be a JSON list of dicts like:\n"
            "[{\"name\": ..., \"court\": ..., \"year\": ..., \"url\": ..., \"confidence\": ...}]\n"
            "Then END the message with 'TERMINATE'."
        ),
        llm_config=llm_config,
    )
            # "4️⃣ If still no data, use `search_web`.\n\n"
    tool_executor = UserProxyAgent(
        name="ToolExecutor",
        llm_config=False,
        human_input_mode="NEVER",
        is_termination_msg=is_termination_msg,
        code_execution_config={"use_docker": False}
    )

    from indiankanoon_api_tool import search_indiankanoon_api
    from google_scholar_tool import search_google_scholar_legal

    precedent_finder.register_for_llm(
        name="search_indian_kanoon",
        description="Search Indian Kanoon for case precedents."
    )(search_indiankanoon_api)

    precedent_finder.register_for_llm(
        name="search_google_scholar_legal",
        description="Search Google Scholar for legal cases."
    )(search_google_scholar_legal)

    # precedent_finder.register_for_llm(
    #     name="search_web",
    #     description="Perform general web search for legal references."
    # )(search_web_wrapper)


    tool_executor.register_for_execution(name="search_indian_kanoon")(search_indiankanoon_api)
    tool_executor.register_for_execution(name="search_google_scholar_legal")(search_google_scholar_legal)
    # tool_executor.register_for_execution(name="search_web")(search_web_wrapper)

    try:
        chat_result = tool_executor.initiate_chat(precedent_finder, message=summary_text)
        history = getattr(chat_result, "chat_history", None)

        if not history:
            return "No precedents found."

        # Look for AI output
        for msg in reversed(history):
            if msg.get("name") == "PrecedentFinderAgent":
                content = msg.get("content", "").replace("TERMINATE", "").strip()

                # Attempt JSON parsing
                json_match = re.search(r"\[(.*?)\]", content, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(f"[{json_match.group(1)}]")
                        formatted = format_precedent_results(parsed)
                        return formatted
                    except Exception as e:
                        print(f"Error parsing JSON: {e}")

                return content or "No precedents found."
        return "No precedents found."
    except Exception as e:
        print(f"Error during precedent finder agent chat: {e}")
        # Fallback: use Google Scholar directly if AI pipeline fails
        try:
            scholar_results = search_google_scholar_legal(summary_text)
            formatted = format_precedent_results(scholar_results)
            return f"⚠️ AI Fallback: Using Google Scholar directly.\n\n{formatted}"
        except Exception as ee:
            print(f"Fallback error: {ee}")
            return f"Failed to find precedents: {e}"


# 🔍 VALIDATION & FORMATTING HELPERS
def _clean_and_validate_results(parsed_list: List[Dict[str, Any]]) -> str:
    cleaned = []
    seen_urls = set()
    for item in parsed_list:
        try:
            name = item.get("name", "").strip()
            court = item.get("court", "").strip()
            year = str(item.get("year", "")).strip()
            url = item.get("url", "").strip()
            confidence = float(item.get("confidence", 0.0))
            if not url and not name:
                continue
            if url in seen_urls:
                continue
            try:
                head = requests.head(url, timeout=3)
                verified = head.status_code < 400
            except Exception:
                verified = False
            seen_urls.add(url)
            cleaned.append({
                "name": name,
                "court": court,
                "year": year,
                "url": url,
                "confidence": round(confidence, 2),
                "verified": verified
            })
        except Exception:
            continue
    if not cleaned:
        return "No structured precedents found."
    return _format_precedent_results_for_ui(cleaned)


def _extract_case_like_entries(text: str) -> List[Dict[str, str]]:
    lines = text.splitlines()
    urls = re.findall(r'https?://\S+', text)
    results = []
    for ln in lines:
        if re.search(r'\b(vs\.?|v\.|versus|v)\b', ln, re.IGNORECASE):
            name = ln.strip()
            nearby_urls = re.findall(r'https?://\S+', ln)
            url = nearby_urls[0] if nearby_urls else ""
            results.append({"name": name, "url": url})
    if not results and urls:
        for u in urls:
            results.append({"name": "", "url": u})
    return results


def _validate_and_dedupe_entries(entries: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    validated = []
    seen = set()
    for e in entries:
        url = e.get("url", "").strip()
        name = e.get("name", "").strip()
        verified = False
        title = name
        if url:
            try:
                resp = requests.head(url, timeout=4, allow_redirects=True)
                verified = resp.status_code < 400
                if not name:
                    try:
                        r2 = requests.get(url, timeout=4)
                        m = re.search(r'<title>(.*?)</title>', r2.text, re.IGNORECASE | re.DOTALL)
                        if m:
                            title = m.group(1).strip()
                    except Exception:
                        pass
            except Exception:
                pass
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)
        validated.append({
            "name": title or "Unknown",
            "url": url,
            "verified": verified,
            "court": "",
            "year": ""
        })
    return validated


def _format_precedent_results_for_ui(results: List[Dict[str, Any]]) -> str:
    parts = ["### Similar Precedents Found"]
    for idx, r in enumerate(results, 1):
        name = r.get("name") or "Unknown Case"
        court = r.get("court")
        year = r.get("year")
        url = r.get("url") or ""
        verified = r.get("verified", False)
        confidence = r.get("confidence", None)
        line = f"{idx}. **{name}**"
        if court:
            line += f" - {court}"
        if year:
            line += f" ({year})"
        parts.append(line)
        if url:
            parts.append(f"   [View Full Case]({url}) {'(verified)' if verified else '(unverified)'}")
        if confidence is not None:
            parts.append(f"   Confidence: {confidence}")
        parts.append("")
    return "\n".join(parts)

import json
import re

def format_json_to_markdown(text: str) -> str:
    """
    Detects and converts JSON-like legal case results into Markdown list format.
    """
    # Try to detect JSON array within text
    json_match = re.search(r'\[.*\]', text, re.DOTALL)
    if not json_match:
        return text  # No JSON found

    try:
        cases = json.loads(json_match.group(0))
        if not isinstance(cases, list):
            return text
        
        formatted = ["### Similar Precedents Found:"]
        for i, case in enumerate(cases, 1):
            name = case.get("name", "Unnamed Case")
            court = case.get("court", "Unknown Court")
            year = case.get("year", "")
            url = case.get("url", "")
            
            entry = f"**{i}. {name}** – {court}"
            if year:
                entry += f" ({year})"
            if url:
                entry += f"\n   [View Full Case]({url})"
            formatted.append(entry)
        return "\n\n".join(formatted)
    except Exception:
        return text  # If parsing fails, just return the original
# ⚙️ SOURCE DETECTION
def get_answer_source(chat_history: List[Dict[str, Any]]) -> str:
    used_local_rag = False
    used_kanoon = False
    used_web = False

    if not chat_history:
        return "General Knowledge"

    for msg in chat_history:
        content = str(msg.get("content", ""))
        if "retrieve_legal_context" in content:
            used_local_rag = True
        if "search_indiankanoon_api" in content:
            used_kanoon = True
        if "search_web" in content:
            used_web = True

    sources = []
    if used_local_rag:
        sources.append("Uploaded Document")
    if used_kanoon:
        sources.append("Indian Kanoon")
    if used_web:
        sources.append("Web Search")

    return " & ".join(sources) if sources else "General Knowledge"
# 💬 MAIN CHAT AGENT
def run_agent(query: str, db_path: Optional[str] = None, summary: Optional[str] = None, pdf_name: Optional[str] = None):
    used_tools = {"local_rag": False, "kanoon": False, "web": False}
    used_tools["local_rag"] = True 
    def retrieve_context_tool(query: str) -> str:
        if not db_path or not os.path.exists(db_path):
            return "NO_INDEX_AVAILABLE"
        return retrieve_legal_context(query, persist_dir=db_path)
    
    def kanoon_tool(query: str):
        used_tools["kanoon"] = True
        return search_indiankanoon_api(query)

    def web_tool(query: str):
        used_tools["web"] = True
        return search_web(query)


    system_message_template = f"""
You are LexiLaw — an intelligent legal AI assistant integrated into a Flask-based app.

You are designed to analyze legal documents, find relevant precedents, and answer general legal or factual questions accurately.

## CONTEXT
- You are currently analyzing this document: "{pdf_name or 'N/A'}"
- Document summary: {summary or 'No summary available.'}

## TOOLS AVAILABLE
1. *retrieve_legal_context(query)* — Retrieve content from the uploaded legal document.
2. *search_indiankanoon_api(query)* — Find related public Indian legal precedents.
3. *search_web(query)* — Search the live internet for general legal or factual information.

## DECISION RULES
1. *Greeting or closing* → Reply politely and end immediately with TERMINATE.
2. *Document-related query* → Use retrieve_legal_context.
   - If it returns "NO_INDEX_AVAILABLE", fall back to the document summary.
3. *Public precedent / case law* → Use search_indiankanoon_api.
   - If no results are found, automatically try search_web.
4. *General query* → Use search_web only if relevant; otherwise answer directly from general knowledge.
5. Always prefer fact-based and concise responses.

## RESPONSE POLICY
- Output *only* the final answer (no steps or internal reasoning).
- Be accurate, formal, and concise.
- Every valid response *must* end with TERMINATE.

consistent, reliable, and direct.
 — just the factual answer followed by `TERMINATE`.
"""


    legal_assistant = AssistantAgent(
        name="LegalAssistant",
        system_message=system_message_template,
        llm_config=llm_config,
    )

    tool_executor = UserProxyAgent(
        name="ToolExecutor",
        llm_config=False,
        human_input_mode="NEVER",
        is_termination_msg=is_termination_msg,
        code_execution_config={"use_docker": False}
    )

    legal_assistant.register_for_llm(name="retrieve_legal_context")(retrieve_context_tool)
    legal_assistant.register_for_llm(name="search_indiankanoon_api")(kanoon_tool)
    legal_assistant.register_for_llm(name="search_web")(web_tool)

    tool_executor.register_for_execution(name="retrieve_legal_context")(retrieve_context_tool)
    tool_executor.register_for_execution(name="search_indiankanoon_api")(kanoon_tool)
    tool_executor.register_for_execution(name="search_web")(web_tool)


    try:
        chat_result = tool_executor.initiate_chat(legal_assistant, message=query)
        history = getattr(chat_result, "chat_history", None)
        if not history:
            return "No chat history found.", [], "Error"

        # Determine actual data source dynamically
        sources = []
        if used_tools["local_rag"]:
            sources.append("Uploaded Document")
        if used_tools["kanoon"]:
            sources.append("Indian Kanoon")
        if used_tools["web"]:
            sources.append("Web Search")
        if not sources:
            sources.append("General Knowledge")
        source = " & ".join(sources)

        for msg in reversed(history):
            if msg.get("name") == "LegalAssistant":
                content = msg.get("content", "").strip()
                if "TERMINATE" in content:
                    return content.replace("TERMINATE", "").strip(), history, source
        return "No valid answer generated.", history, "Error"
    except Exception as e:
        error_text = str(e)
        if "503" in error_text or "UNAVAILABLE" in error_text:
            return "Gemini is currently overloaded. Please try again in a few seconds.", [], "Gemini Service"
        print(f"Error during agent chat: {e}")
        return f"Error: {e}", [], "Error"
    
# 🌐 API ROUTES
@app.route("/")
def serve_index():
    return send_from_directory('.', 'index.html')


@app.route("/<path:path>")
def serve_static(path):
    if path in ('style.css', 'script.js'):
        return send_from_directory('.', path)
    return jsonify({"detail": "Not found"}), 404


@app.route("/signup", methods=["POST"])
def signup_user():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    success, message = add_user(username, password)
    if success:
        return jsonify({"message": message}), 201
    return jsonify({"detail": message}), 400

@app.route("/login", methods=["POST"])
def login_user():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    user_id = check_user(username, password)
    if user_id is None:
        return jsonify({"detail": "Incorrect username or password"}), 401

    access_token = create_access_token(identity=str(user_id))
    summary, pdf_name = load_document_summary(user_id)
    chat_history = load_chat_history(user_id)
    precedents = load_precedents2(user_id)


    return jsonify({
        "message": "Login successful",
        "access_token": access_token,
        "username": username,
        "user_id": user_id,
        "summary": summary,
        "pdf_name": pdf_name,
        "chat_history": chat_history,
        "precedents": precedents # ✅ Send precedents to frontend
    }), 200



@app.route("/upload", methods=["POST"])
@jwt_required()
def upload_file():
    user_id = int(get_jwt_identity())
    if 'file' not in request.files:
        return jsonify({"detail": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"detail": "No selected file"}), 400
    if not file.filename.endswith(".pdf"):
        return jsonify({"detail": "Invalid file type. Only PDF allowed."}), 400

    filename = secure_filename(file.filename)
    os.makedirs("docs", exist_ok=True)
    pdf_save_path = os.path.join("docs", filename)
    file.save(pdf_save_path)

    full_text = get_full_text_from_pdf(pdf_save_path)
    summary = run_summarizer_agent(full_text)
    save_document_summary(user_id, summary, filename)

    user_db_path = f"chroma_db_user_{user_id}"
    if os.path.exists(user_db_path):
        shutil.rmtree(user_db_path)
    build_index_from_pdf(pdf_save_path, persist_dir=user_db_path)

    return jsonify({
        "message": "File uploaded and indexed successfully.",
        "summary": summary,
        "pdf_name": filename
    }), 200


@app.route("/chat", methods=["POST"])
@jwt_required()
def chat():
    user_id = int(get_jwt_identity())
    data = request.json
    query = data.get("query")

    if not query:
        return jsonify({"detail": "Query is required."}), 400

    summary, pdf_name = load_document_summary(user_id)
    user_db_path = f"chroma_db_user_{user_id}"

    save_chat_message(user_id, "user", query)
    answer, raw_history, source = run_agent(query, user_db_path, summary, pdf_name)
    save_chat_message(user_id, "assistant", answer, source)
    formatted_answer = format_json_to_markdown(answer)

    # --- FACT CHECK START ---
    fact_results = []  # ✅ always initialize
    try:
        from fact_checker import fact_checker_agent
        from tools import retrieve_legal_context
        from database import save_fact_check_results

        context_text = retrieve_legal_context(query, persist_dir=user_db_path)
        retrieved_chunks = context_text.split("\n\n")[:5] if context_text else []

        if retrieved_chunks:
            print(f"[FACT CHECK] Running for query: {query[:60]}...")
            fact_results = fact_checker_agent(answer, retrieved_chunks)
            if fact_results and isinstance(fact_results, list):
                save_fact_check_results(user_id, fact_results)
        else:
            fact_results = [{"error": "No valid evidence for fact check."}]
            print("[FACT CHECK] Skipped: no retrieved context.")
    except Exception as e:
        fact_results = [{"error": f"Fact check failed: {e}"}]
        print(f"[FACT CHECK ERROR] {e}")
    # --- FACT CHECK END ---

    return jsonify({
        "answer": formatted_answer,
        "source": source,
        "fact_check": fact_results   # ✅ Always included
    }), 200

def format_precedent_html(item):
    title = item.get("name") or item.get("title") or "Unnamed"
    court = item.get("court") or "N/A"
    year = item.get("year") or "N/A"
    url = item.get("url") or "#"

    return f"""
    <div class='precedent'>
        <strong>{title}</strong><br>
        {court} ({year})<br>
        <a href="{url}" target="_blank">Read</a>
        <hr>
    </div>
    """


@app.route("/fact-history", methods=["GET"])
@jwt_required()
def get_fact_history():
    user_id = int(get_jwt_identity())
    from database import load_fact_check_history
    history = load_fact_check_history(user_id)
    return jsonify({"history": history}), 200

import json

# @app.route("/find-precedents", methods=["POST"])
# @jwt_required()
# def find_precedents():
#     user_id = int(get_jwt_identity())
#     summary, _ = load_document_summary(user_id)

#     if not summary:
#         return jsonify({"detail": "No summary found. Please upload a document first."}), 400

#     precedents_formatted = run_precedent_finder_agent(summary)

#     try:
#         precedents_list = search_indiankanoon_api(summary, limit=5)
#         save_precedents2(user_id, precedents_list, precedents_formatted)
#     except Exception as e:
#         print(f"[DB SAVE ERROR] {e}")
#         precedents_list = []

#     return jsonify({
#         "precedents": precedents_formatted,
#         "saved_precedents": precedents_list
#     }), 200

@app.route("/find-precedents", methods=["POST"])
@jwt_required()
def find_precedents():
    user_id = int(get_jwt_identity())
    summary, _ = load_document_summary(user_id)

    if not summary:
        return jsonify({"detail": "No summary found. Please upload a document first."}), 400

    # Generate AI formatted precedents
    precedents_formatted = run_precedent_finder_agent(summary)

    # Extract query (optional)
    body = request.get_json(silent=True) or {}
    query = body.get("query", summary)

    try:
        # Get Indian Kanoon results
        precedents_list = search_indiankanoon_api(query, limit=5)

        # Save both Kanoon results and AI formatted precedents
        save_precedents2(user_id, precedents_list, precedents_formatted)

    except Exception as e:
        print(f"[DB SAVE ERROR] {e}")
        precedents_list = []

    return jsonify({
        "precedents": precedents_formatted,  # AI summary precedents
        "saved_precedents": precedents_list  # saved IKanoon cases
    }), 200

from flask_jwt_extended import jwt_required, get_jwt_identity
import sqlite3

def save_precedents2(user_id: int, precedents_list: list, formatted_ai: str):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    for item in precedents_list:
        c.execute("""
            INSERT INTO precedents2 (user_id, title, court, year, url, confidence, ai_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            item.get("name") or item.get("title"),
            item.get("court", ""),
            item.get("year", ""),
            item.get("url", ""),
            item.get("confidence", 1.0),
            formatted_ai  # Store the AI-formatted precedents summary
        ))

    conn.commit()
    conn.close()



def load_precedents2(user_id: int):
    with sqlite3.connect("users.db") as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, court, year, url, confidence, ai_summary, created_at
            FROM precedents2
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 50
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]


# @app.route("/get-precedents-json", methods=["GET"])
# @jwt_required()
# def get_precedents_json():
#     user_id = int(get_jwt_identity())
#     precedents = load_precedents2(user_id)
#     return jsonify(precedents), 200

@app.route("/get-precedents", methods=["GET"])
@jwt_required()
def get_precedents():
    user_id = int(get_jwt_identity())
    precedents_raw = load_precedents2(user_id)

    # Extract the AI formatted markdown summary from the most recent entry
    formatted_md = precedents_raw[0]["ai_summary"] if precedents_raw else ""

    return jsonify({
        "formatted_markdown": formatted_md,  # Beautiful formatted summary
        "precedents_json": precedents_raw    # Full structured JSON list
    }), 200


@app.route("/find-lawyers", methods=["POST"])
def find_lawyers():
    data = request.json
    latitude = data.get("lat")
    longitude = data.get("lon")
    radius = data.get("radius", 5000)  # default 5 km

    api_key = os.getenv("GEOAPIFY_API_KEY")
    if not api_key:
        return jsonify({"error": "Missing Geoapify API key"}), 500

    url = f"https://api.geoapify.com/v2/places?categories=legal.lawyer&filter=circle:{longitude},{latitude},{radius}&limit=20&apiKey={api_key}"

    res = requests.get(url)
    return jsonify(res.json())



import traceback

@app.errorhandler(Exception)
def handle_exception(e):
    """Return errors as JSON so the frontend can handle them."""
    tb = traceback.format_exc()
    print(f"[Server Error] {tb}")
    return jsonify({
        "detail": "Internal Server Error",
        "error": str(e),
        "trace": tb if app.debug else None
    }), 500

# --- Main ---
if __name__ == "__main__":
    db_init() # Ensure DB is set up
    print("Flask server starting on http://127.0.0.1:8000")
    app.run(debug=True, port=8000)