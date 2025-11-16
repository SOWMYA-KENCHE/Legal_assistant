import os
import requests

IKANOON_API_URL = "https://api.indiankanoon.org/search/"
IKANOON_API_TOKEN = os.getenv("INDIAN_KANOON_API_TOKEN")


def search_indiankanoon_api(query: str, limit: int = 5) -> list[dict]:
    """
    Search Indian Kanoon API for legal precedents using POST.
    Fixes 405 Method Not Allowed error.
    """

    if not IKANOON_API_TOKEN:
        print("[IKANOON ERROR] Missing API token in environment (.env)")
        return [{
            "name": "Error: Missing Indian Kanoon API token.",
            "court": "",
            "year": "",
            "url": "",
            "confidence": 0
        }]

    if not query or not query.strip():
        return [{
            "name": "Error: Empty query provided.",
            "court": "",
            "year": "",
            "url": "",
            "confidence": 0
        }]

    # 🧠 STEP 1 — Truncate query (first 30 words only)
    words = query.split()
    short_query = " ".join(words[:30])

    headers = {
        "Authorization": f"Token {IKANOON_API_TOKEN}",
        "Accept": "application/json",
    }

    # 🟢 Indian Kanoon REQUIRES POST now
    payload = {
        "formInput": short_query,
        "pagenum": 0,
        "maxpages": 1
    }

    try:
        print(f"[IKANOON DEBUG] Querying short: {short_query[:120]}...")

        # 🚀 FIX: use POST instead of GET
        res = requests.post(
            IKANOON_API_URL,
            headers=headers,
            data=payload,
            timeout=10
        )

        print(f"[IKANOON DEBUG] Status: {res.status_code}")

        res.raise_for_status()
        data = res.json()

        # No docs returned
        if "docs" not in data or not data["docs"]:
            return [{
                "name": "No matching cases found on Indian Kanoon.",
                "court": "",
                "year": "",
                "url": "",
                "confidence": 0.0
            }]

        precedents = []
        for doc in data["docs"][:limit]:
            precedents.append({
                "name": doc.get("title", "Untitled"),
                "year": doc.get("year", ""),
                "court": doc.get("docsource", ""),
                "url": f"https://indiankanoon.org/doc/{doc.get('tid', '')}/",
                "confidence": 1.0
            })

        print(f"[IKANOON DEBUG] ✅ Retrieved {len(precedents)} results.")
        return precedents

    except requests.exceptions.Timeout:
        print("[IKANOON ERROR] Request timed out.")
        return [{
            "name": "Indian Kanoon request timed out.",
            "court": "",
            "year": "",
            "url": "",
            "confidence": 0
        }]

    except requests.exceptions.HTTPError as e:
        print(f"[IKANOON ERROR] HTTPError: {e}")
        return [{
            "name": f"Indian Kanoon API Error: {e}",
            "court": "",
            "year": "",
            "url": "",
            "confidence": 0
        }]

    except Exception as e:
        print(f"[IKANOON ERROR] Unexpected: {e}")
        return [{
            "name": f"Unexpected error: {e}",
            "court": "",
            "year": "",
            "url": "",
            "confidence": 0
        }]
