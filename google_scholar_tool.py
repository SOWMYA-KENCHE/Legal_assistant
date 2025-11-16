import os
from serpapi import GoogleSearch
from dotenv import load_dotenv

load_dotenv()

def search_google_scholar_legal(query: str, limit: int = 5) -> list[dict]:
    """
    Searches Google Scholar for legal cases via SerpAPI and returns structured results.
    """
    import os
    from serpapi import GoogleSearch

    try:
        params = {
            "engine": "google_scholar",
            "q": query,
            "hl": "en",
            "api_key": os.getenv("SERPAPI_KEY"),
        }

        search = GoogleSearch(params)
        results = search.get_dict()
        organic = results.get("organic_results", [])
        parsed = []

        for item in organic[:limit]:
            title = item.get("title", "Unnamed Case")
            snippet = item.get("snippet", "")
            year, court = "", ""
            link = item.get("link", "")

            # 🩵 FIX: always build a valid fallback link
            if not link or "scholar_case" in link:
                link = f"https://scholar.google.com/scholar?q={title.replace(' ', '+')}"

            # try extracting year or court name
            publication_info = item.get("publication_info", {}).get("summary", "")
            if publication_info:
                parts = publication_info.split(" - ")
                court = parts[-1] if len(parts) > 1 else ""
                year = next((p for p in parts if p.strip().isdigit()), "")

            parsed.append({
                "name": title,
                "court": court,
                "year": year,
                "url": link,
                "confidence": 0.75,
                "snippet": snippet,
            })

        if not parsed:
            return [{"name": "No Google Scholar results found.", "url": "", "confidence": 0}]

        return parsed
    except Exception as e:
        print(f"[Google Scholar Error] {e}")
        return [{"name": f"Google Scholar Error: {e}", "url": "", "confidence": 0}]

