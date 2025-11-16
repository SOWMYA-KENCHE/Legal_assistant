import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
# --- FIX for LangChainDeprecationWarning ---
from langchain_chroma import Chroma # <-- NEW IMPORT
# --- END OF FIX ---
from typing import Tuple
from langchain_core.documents import Document
import time # For the file lock fix

load_dotenv()

# ------------------ TOOL FUNCTION ------------------
def load_chroma(persist_dir="chroma_db", model_name="sentence-transformers/all-MiniLM-L6-v2"):
    """Loads the Chroma vector database from the persist directory."""
    embeddings = HuggingFaceEmbeddings(model_name=model_name)
    vectordb = Chroma(persist_directory=persist_dir, embedding_function=embeddings)
    return vectordb

def retrieve_legal_context(
    query: str,
    persist_dir: str = "chroma_db",
    k: int = 5,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
) -> str:
    """
    Retrieve top-k similar document chunks from Chroma for the given query.
    Returns a single concatenated context string (JSON-serializable).
    """
    try:
        if not os.path.exists(persist_dir):
            return "NO_INDEX_AVAILABLE"
            
        vectordb = load_chroma(persist_dir=persist_dir, model_name=model_name)
    except Exception as e:
        print(f"Error loading Chroma DB from {persist_dir} : {e}")
        # Give the system a moment if it's a file lock error
        if "unable to open database file" in str(e):
             time.sleep(1)
             try:
                 vectordb = load_chroma(persist_dir=persist_dir, model_name=model_name)
             except Exception as e2:
                 print(f"Retry failed: {e2}")
                 return f"Error loading Chroma DB: {e2}. Please ensure you have uploaded a document first."
        else:
            return f"Error loading Chroma DB: {e}. Please ensure you have uploaded a document first."

    docs = vectordb.similarity_search(query, k=k)
    
    # --- FIX for file lock: Explicitly delete the object ---
    try:
        del vectordb
    except:
        pass # Fail silently
    # --- END OF FIX ---
    
    if not docs:
        return "No relevant context was found in the document for your query."
        
    context = "\n\n".join([getattr(d, "page_content", str(d)) for d in docs])
    return context

