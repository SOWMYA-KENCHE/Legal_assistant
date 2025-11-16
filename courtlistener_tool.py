# courtlistener_tool.py
import requests

def search_courtlistener(query: str, limit: int = 5):
    """
    Search U.S. court cases using the CourtListener API.

    Args:
        query (str): Search text (e.g., 'breach of contract')
        limit (int): Number of cases to fetch (default: 5)

    Returns:
        list[dict]: Structured list of cases (name, court, year, url)
    """
    base_url = "https://www.courtlistener.com/api/rest/v3/search/"
    params = {
        "q": query,
        "type": "opinion",
        "page_size": limit,
        "order_by": "score"
    }

    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = []

        for case in data.get("results", []):
            name = case.get("caseName", "Unknown Case")
            court_name = case.get("court", {}).get("name", "Unknown Court")
            date_filed = case.get("dateFiled", "Unknown Date")
            year = date_filed.split("-")[0] if "-" in date_filed else "N/A"
            url = f"https://www.courtlistener.com{case.get('absolute_url', '')}"

            results.append({
                "name": name,
                "court": court_name,
                "year": year,
                "url": url,
                "confidence": 0.95  # Static confidence for now
            })

        if not results:
            return [{"name": "No cases found.", "url": "", "court": "", "year": "", "confidence": 0}]

        return results

    except requests.exceptions.RequestException as e:
        print(f"[CourtListener Error] {e}")
        return [{"name": f"API Error: {e}", "url": "", "court": "", "year": "", "confidence": 0}]
