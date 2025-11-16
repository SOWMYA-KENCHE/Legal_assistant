# import google.generativeai as genai
# from dotenv import load_dotenv
# import os
# import json
# import re

# # Load environment variables
# load_dotenv()
# genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# # You can switch models if needed
# MODEL = "gemini-2.5-flash"  # or "gemini-2.0-flash", "gemini-pro"

# def fact_checker_agent(answer: str, retrieved_chunks: list[str]) -> list[dict]:
#     """
#     Fact-check the overall assistant answer against retrieved evidence,
#     rather than breaking it into sub-statements.
#     """
#     import google.generativeai as genai
#     import json, re, os
#     from dotenv import load_dotenv
#     load_dotenv()
#     genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

#     MODEL = "gemini-2.5-flash"

#     if not answer.strip():
#         return [{"error": "No answer provided for fact checking."}]
#     if not retrieved_chunks:
#         return [{"error": "No evidence chunks found to verify facts."}]

#     evidence_text = "\n\n".join(retrieved_chunks[:10])

#     prompt = f"""
# You are a FACT-CHECKING expert.
# Given an assistant's answer and retrieved evidence, evaluate whether the answer
# is *factually supported* by the evidence as a whole.
# Return strictly valid JSON in this format:
# [
#   {{
#     "statement": "...",
#     "supported": true/false,
#     "confidence": 0.00,
#     "evidence": "..."
#   }}
# ]

# ----------------
# Answer:
# {answer}

# ----------------
# Evidence:
# {evidence_text}
# """

#     try:
#         model = genai.GenerativeModel(MODEL)
#         response = model.generate_content(prompt)
#         raw_output = response.text.strip()
#         print("[FACT CHECK RAW OUTPUT]", raw_output)

#         # Try to parse clean JSON
#         match = re.search(r"\{.*\}", raw_output, flags=re.S)
#         if match:
#             return [json.loads(match.group(0))]

#         return [{"error": "Could not parse Gemini output.", "raw_output": raw_output}]
#     except Exception as e:
#         return [{"error": f"Fact-checking failed: {e}"}]

import os
import json
import re
from dotenv import load_dotenv
import google.generativeai as genai

# Load Gemini API Key
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "gemini-2.5-flash"

# -------------------------
# Helper: Remove trivial/greeting lines
# -------------------------
def _filter_trivial_sentences(text: str) -> str:
    """
    Remove greetings, short fillers, and trivial lines from the assistant answer
    before sending it to the fact-checking model.
    """
    lines = [ln.strip() for ln in re.split(r'[\r\n]+', text) if ln.strip()]
    useful = []
    for ln in lines:
        lower = ln.lower()
        if any(word in lower for word in [
            "hello", "hi", "hey", "good morning", "good evening", 
            "how can i help", "how can i assist"
        ]):
            continue
        if len(ln.split()) <= 3:
            continue
        useful.append(ln)
    return "\n\n".join(useful) if useful else text


# -------------------------
# Main Function
# -------------------------
def fact_checker_agent(answer: str, retrieved_chunks: list[str]) -> list[dict]:
    """
    Runs Gemini-based fact-checking on the full assistant answer as one unit.

    Args:
        answer (str): Assistant's final full response.
        retrieved_chunks (list[str]): List of evidence text chunks from RAG.

    Returns:
        list[dict]: Structured fact-checking results:
            [
                {
                    "statement": "...",
                    "supported": True/False,
                    "confidence": 0.00–1.00,
                    "evidence": "..."
                }
            ]
    """

    # Basic validations
    if not answer or not answer.strip():
        return [{"error": "No answer provided for fact checking."}]

    if not retrieved_chunks:
        return [{"error": "No evidence chunks found to verify facts."}]

    # Prepare evidence (keep top 8 chunks to avoid prompt overflow)
    evidence_text = "\n\n".join(retrieved_chunks[:8])

    # Clean the answer (remove greetings etc.)
    cleaned_answer = _filter_trivial_sentences(answer)

    # Prompt for Gemini
    prompt = f"""
You are a FACT-CHECKER specializing in **Indian legal content**.

Your goal is to check whether the factual claims in the ASSISTANT'S ANSWER
are supported by the provided EVIDENCE (retrieved from legal documents or judgments).

### INSTRUCTIONS
1️⃣ Examine the full answer holistically — do NOT treat each sentence separately.
2️⃣ Identify only meaningful factual statements (ignore greetings or opinion words).
3️⃣ For each factual statement:
     - Determine whether it is **supported** by the evidence.
     - If supported, include a short direct quote from the evidence (<=200 chars).
     - If unsupported, write "NO SUPPORT IN RETRIEVED EVIDENCE".
     - Provide a confidence score between 0.00 and 1.00.
4️⃣ Return valid JSON **only**, in this structure:

[
  {{
    "statement": "...",
    "supported": true/false,
    "confidence": 0.00,
    "evidence": "..."
  }}
]

### ASSISTANT ANSWER
{cleaned_answer}

### EVIDENCE (retrieved legal context)
{evidence_text}

Important:
- Output ONLY JSON, without markdown or commentary.
- Avoid repetition or extra text outside JSON.
"""

    try:
        model = genai.GenerativeModel(MODEL)
        response = model.generate_content(prompt)
        raw_output = response.text.strip()

        # Strip ```json fences if model wraps output
        raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output)
        raw_output = re.sub(r"\s*```$", "", raw_output)

        # Try to parse JSON
        try:
            return json.loads(raw_output)
        except json.JSONDecodeError:
            # Extract only JSON array if model added text
            match = re.search(r"\[.*\]", raw_output, flags=re.S)
            if match:
                return json.loads(match.group(0))
            else:
                return [{"error": "Fact-checker returned non-JSON output", "raw_output": raw_output}]

    except Exception as e:
        return [{"error": f"Gemini Fact-Checker Error: {str(e)}"}]
