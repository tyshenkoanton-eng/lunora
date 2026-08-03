import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "Lunora/0.1 (astro mini-app)"}


async def geocode_city(query: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "limit": 5,
                "accept-language": "ru",
                "featuretype": "city",
            },
            headers=HEADERS,
        )
        resp.raise_for_status()
        results = resp.json()

    return [
        {
            "name": r.get("display_name", ""),
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
        }
        for r in results
        if "lat" in r and "lon" in r
    ]
