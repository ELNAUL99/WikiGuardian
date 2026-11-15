from app.agents.oxylabs_client import (
    OxylabsClient,
    OxylabsAPIError,
)


with OxylabsClient() as client:

    print("Testing Oxylabs search...")

    results = client.search(
        query="Helsinki capital of Finland official",
        max_results=3,
    )

    if not results:
        raise RuntimeError("Search returned no results.")

    print("SEARCH TEST: SUCCESS")
    print("Results:", len(results))

    first = results[0]

    url = first.get("url")

    if not url:
        raise RuntimeError("First result has no URL.")

    print("\nTesting page scraping...")
    print("Selected:", first.get("title"))

    page = client.scrape(url)

    markdown = page.get("markdown", "")

    if not markdown:
        raise RuntimeError(
            "Scraping succeeded but returned no Markdown content."
        )

    print("SCRAPE TEST: SUCCESS")
    print("Scraped URL:", page.get("url", url))
    print("Content length:", len(markdown))
    print("\nContent preview:")
    print(markdown[:500])

print("\nOXYLABS CLIENT TEST: SUCCESS")
