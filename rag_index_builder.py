import fitz  # PyMuPDF
import os
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
# from langchain.embeddings import HuggingFaceEmbeddings


# Load environment variables
load_dotenv()

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts text from a PDF using PyMuPDF."""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text

def build_index_from_pdf(pdf_path: str, persist_dir: str = "chroma_db", model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
    """
    Builds a Chroma vector index from a PDF file.
    
    This function now uses langchain-chroma and removes the deprecated .persist() call.
    """
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=50)
    docs = splitter.split_documents(docs)

    embeddings = HuggingFaceEmbeddings(model_name=model_name)
    
    # Create the vector store. This now automatically persists to the directory.
    vectordb = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=persist_dir
    )
    
    # The .persist() method is no longer needed in this version of langchain-chroma.
    # vectordb.persist() # <-- This line was removed as it caused the error.
    
    print(f"✅ Vector index built and saved to {persist_dir}")
    return vectordb

if __name__ == "__main__":
    # This block is for testing only.
    # It will not run when imported by app.py.
    if not os.path.exists("docs"):
        os.makedirs("docs")
    
    # Create a dummy PDF for testing if it doesn't exist
    dummy_pdf_path = "./docs/dummy_test.pdf"
    if not os.path.exists(dummy_pdf_path):
        try:
            doc = fitz.open() # Create a new PDF
            page = doc.new_page()
            page.insert_text((72, 72), "This is a test document for rag_index_builder.py.")
            doc.save(dummy_pdf_path)
            doc.close()
            print(f"Created dummy PDF: {dummy_pdf_path}")
        except Exception as e:
            print(f"Could not create dummy PDF: {e}")

    # Test the index building
    if os.path.exists(dummy_pdf_path):
        print(f"Testing index building with {dummy_pdf_path}...")
        build_index_from_pdf(dummy_pdf_path, persist_dir="chroma_test_db")
    else:
        print("Skipping index building test, dummy PDF not found.")


