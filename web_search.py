
import os
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()


def search_web(question, max_results=3):
    """Search the web and return results with their source URLs."""

    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        return {
            "success": False,
            "error": "TAVILY_API_KEY is not configured.",
            "results": [],
        }

    try:
        client = TavilyClient(api_key=api_key)

        response = client.search(
            query=question,
            search_depth="basic",
            max_results=max_results,
        )

        results = []

        for item in response.get("results", []):
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            content = item.get("content", "").strip()

            if title and url and content:
                results.append({
                    "title": title,
                    "url": url,
                    "content": content,
                })

        return {
            "success": True,
            "error": None,
            "results": results,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
            "results": [],
        }
