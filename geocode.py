"""Geolocation and Reverse Geocoding Utility for ThoughtStash."""

import json
import urllib.parse
import urllib.request

USER_AGENT = "ThoughtStash-VoiceApp/1.0"

# Quick local dictionary of common Bay Area walk locations for instant sub-millisecond lookup
KNOWN_BAY_AREA_SPOTS = {
    "rancho san antonio": {
        "name": "Rancho San Antonio Preserve, Cupertino",
        "lat": 37.3328,
        "lon": -122.0864,
    },
    "stanford": {
        "name": "Stanford University Campus, Palo Alto",
        "lat": 37.4275,
        "lon": -122.1697,
    },
    "stanford dish": {
        "name": "Stanford Dish Trail, Stanford",
        "lat": 37.4172,
        "lon": -122.1736,
    },
    "shoreline": {
        "name": "Shoreline Lake Park, Mountain View",
        "lat": 37.4302,
        "lon": -122.0824,
    },
    "castro": {
        "name": "Castro Street, Downtown Mountain View",
        "lat": 37.3942,
        "lon": -122.0795,
    },
    "burlingame": {
        "name": "Burlingame Avenue, Burlingame",
        "lat": 37.5779,
        "lon": -122.3481,
    },
    "palo alto": {
        "name": "Downtown Palo Alto, CA",
        "lat": 37.4419,
        "lon": -122.1430,
    },
    "mission": {
        "name": "Mission Dolores Park, San Francisco",
        "lat": 37.7596,
        "lon": -122.4269,
    },
    "ferry building": {
        "name": "Embarcadero & Ferry Building, San Francisco",
        "lat": 37.7955,
        "lon": -122.3937,
    },
    "crissy field": {
        "name": "Crissy Field, Presidio, San Francisco",
        "lat": 37.8039,
        "lon": -122.4651,
    },
    "cupertino": {
        "name": "Cupertino Memorial Park, Cupertino",
        "lat": 37.3230,
        "lon": -122.0322,
    },
}


def reverse_geocode(lat: float, lon: float) -> str:
  """Convert latitude and longitude into a clean, human-readable address."""
  try:
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=16"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=3) as resp:
      data = json.loads(resp.read().decode())
      addr = data.get("address", {})

      # Extract most relevant human-readable components
      poi = addr.get("amenity") or addr.get("tourism") or addr.get("leisure")
      road = (
          addr.get("road") or addr.get("pedestrian") or addr.get("suburb") or ""
      )
      city = (
          addr.get("city")
          or addr.get("town")
          or addr.get("village")
          or addr.get("municipality")
          or ""
      )
      state = addr.get("state") or ""

      parts = []
      if poi:
        parts.append(poi)
      if road:
        parts.append(road)
      if city:
        parts.append(city)
      elif state:
        parts.append(state)

      if parts:
        return ", ".join(parts)
      return data.get("display_name", f"{lat:.4f}, {lon:.4f}")
  except Exception:
    # Nearest known spot if network lookup fails
    return f"{lat:.4f}, {lon:.4f}"


def search_place(query: str) -> dict | None:
  """Search a place name and return { name, lat, lon }."""
  if not query or not query.strip():
    return None

  q_clean = query.strip().lower()
  for key, val in KNOWN_BAY_AREA_SPOTS.items():
    if key in q_clean:
      return val

  try:
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={urllib.parse.quote(query)}&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=3) as resp:
      data = json.loads(resp.read().decode())
      if data and len(data) > 0:
        item = data[0]
        # Clean display name to first 3 segments
        display_parts = item["display_name"].split(",")[:3]
        clean_name = ", ".join(p.strip() for p in display_parts)
        return {
            "name": clean_name,
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
        }
  except Exception:
    pass

  return None
