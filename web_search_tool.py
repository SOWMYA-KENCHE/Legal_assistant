import os
import requests
from dotenv import load_dotenv
from tavily import TavilyClient
from typing import List, Dict, Any

# Load environment variables
load_dotenv()

def search_web(query: str) -> str:
    """
    Searches the web using the Tavily Search API for a given query.
    Requires TAVILY_API_KEY to be set in the .env file.
    """
    
    api_key = os.getenv("TAVILY_API_KEY")
    
    if not api_key:
        return "Error: TAVILY_API_KEY is not set in the .env file."

    try:
        client = TavilyClient(api_key=api_key)
        # include_answer=True adds an AI-generated answer based on the results
        response = client.search(query=query, search_depth="basic", include_answer=True, max_results=3)
        
        # Format the results for the LLM
        context = f"Tavily Search Answer: {response.get('answer', 'No answer found.')}\n\nSources:\n"
        for result in response.get("results", []):
            context += f"- **Title:** {result.get('title')}\n"
            context += f"  **Content:** {result.get('content')}\n"
            context += f"  **URL:** {result.get('url')}\n\n"
            
        return context

    except Exception as e:
        print(f"Error during Tavily search: {e}")
        return f"An unexpected error occurred while searching the web: {e}"

if __name__ == "__main__":
    # Test the function (requires .env file with token)
    test_query = "latest news on Indian contract law 2024"
    print(f"Testing Tavily API with query: '{test_query}'")
    results = search_web(test_query)
    print(results)