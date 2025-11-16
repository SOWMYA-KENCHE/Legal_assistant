# Legal RAG Assistant

A Retrieval-Augmented Generation (RAG) assistant for legal document analysis and question answering, built with Streamlit. This project helps users interactively query legal documents and receive AI-powered responses.

## Setup Instructions

1. **Clone the repository**
   ```sh
   git clone <repo-url>
   cd legal-rag-assistant
   ```

2. **Create a virtual environment**
   ```sh
   python -m venv myenv
   ```

3. **Activate the virtual environment**

   - On Windows:
     ```sh
     myenv\Scripts\activate
     ```
   - On macOS/Linux:
     ```sh
     source myenv/bin/activate
     ```

4. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   ```

5. **Set up environment variables**
   - Copy `.env.example` to `.env` and update values as needed.

6. **Run the Streamlit app**
   ```sh
   streamlit run app.py
   ```

