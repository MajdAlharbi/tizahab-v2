"""Small source adapters. Provider outages never affect catalogue reads."""

import math
import requests
from django.conf import settings


class ProviderBlocked(Exception):
    pass


class ProviderError(Exception):
    pass


def fetch_osm():
    user_agent = getattr(settings, "CATALOG_USER_AGENT", "").strip()
    if not user_agent:
        raise ProviderBlocked(
            "Configure an identifying CATALOG_USER_AGENT with a contact before using the public Overpass instance."
        )
    query = """[out:json][timeout:25];(
      nwr["tourism"~"^(attraction|museum|gallery|viewpoint)$"](24.35,46.3,25.1,47.05);
      nwr["historic"](24.35,46.3,25.1,47.05);
      nwr["leisure"~"^(park|theme_park)$"](24.35,46.3,25.1,47.05);
      nwr["amenity"~"^(restaurant|cafe|theatre)$"](24.35,46.3,25.1,47.05);
    );out center tags 1000;"""
    try:
        response = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            headers={"User-Agent": user_agent},
            timeout=(5, 35),
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 200 or len(response.content) > 10_000_000:
            raise ProviderError("Unexpected or oversized provider response.")
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        # Do not persist exception URLs, credentials, response bodies or headers.
        raise ProviderError(
            f"OpenStreetMap unavailable ({type(exc).__name__}). Local catalogue preserved."
        ) from None
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ProviderError("Invalid Overpass response.")
    records = []
    for item in payload["elements"][:1000]:
        if not isinstance(item, dict):
            raise ProviderError("Invalid Overpass element.")
        tags = item.get("tags", {})
        title = tags.get("name:en") or tags.get("name")
        if not title:
            continue
        center = item.get("center") or item
        try:
            latitude, longitude = float(center["lat"]), float(center["lon"])
            if not (
                math.isfinite(latitude)
                and math.isfinite(longitude)
                and 24.35 <= latitude <= 25.1
                and 46.3 <= longitude <= 47.05
            ):
                raise ValueError
            external_id = f'{item["type"]}/{int(item["id"])}'
            if item["type"] not in ("node", "way", "relation"):
                raise ValueError
        except (TypeError, KeyError, ValueError):
            raise ProviderError(
                "Provider returned invalid Riyadh coordinates or identifiers."
            ) from None
        category = (
            "heritage"
            if tags.get("historic")
            else (
                "food"
                if tags.get("amenity") in ("restaurant", "cafe")
                else (
                    "nature"
                    if tags.get("leisure") == "park"
                    else (
                        "entertainment"
                        if tags.get("leisure") == "theme_park"
                        or tags.get("amenity") == "theatre"
                        else "culture"
                    )
                )
            )
        )
        records.append(
            {
                "external_id": external_id,
                "title": title,
                "description": tags.get("description:en")
                or tags.get("description", ""),
                "category": category,
                "location": tags.get("addr:street", "Riyadh"),
                "latitude": latitude,
                "longitude": longitude,
                "opening_hours_text": tags.get("opening_hours", ""),
                "source": "OpenStreetMap contributors",
                "source_url": f"https://www.openstreetmap.org/{external_id}",
                "source_license": "ODbL 1.0",
                "price": None,
                "rating": None,
            }
        )
    return records


def fetch_ticketmaster():
    raise ProviderBlocked(
        "Ticketmaster requires a developer key, verified Riyadh coverage and agreed storage/retention rights. Live import is disabled."
    )


ADAPTERS = {"osm": fetch_osm, "ticketmaster": fetch_ticketmaster}
