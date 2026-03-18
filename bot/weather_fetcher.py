"""
Weather Fetcher — NOAA (US) + OpenWeatherMap (international) forecast data.
"""

import requests
from typing import Optional
from utils.logger import log
from utils.helpers import retry_with_backoff, noaa_limiter, fahrenheit_to_celsius, normalize_city_name
from config.settings import settings


# ── Well-known city coordinates (for NOAA grid lookup or OWM) ──
CITY_COORDS: dict[str, tuple[float, float]] = {
    "New York": (40.7128, -74.0060),
    "Los Angeles": (34.0522, -118.2437),
    "Chicago": (41.8781, -87.6298),
    "Houston": (29.7604, -95.3698),
    "Phoenix": (33.4484, -112.0740),
    "Philadelphia": (39.9526, -75.1652),
    "San Antonio": (29.4241, -98.4936),
    "San Diego": (32.7157, -117.1611),
    "Dallas": (32.7767, -96.7970),
    "Miami": (25.7617, -80.1918),
    "Denver": (39.7392, -104.9903),
    "Las Vegas": (36.1699, -115.1398),
    "Seattle": (47.6062, -122.3321),
    "Atlanta": (33.7490, -84.3880),
    "Boston": (42.3601, -71.0589),
    "San Francisco": (37.7749, -122.4194),
    "Washington": (38.9072, -77.0369),
    "Nashville": (36.1627, -86.7816),
    "Austin": (30.2672, -97.7431),
    "Portland": (45.5152, -122.6784),
    # International cities (for OWM fallback)
    "Shanghai": (31.2304, 121.4737),
    "Tokyo": (35.6762, 139.6503),
    "London": (51.5074, -0.1278),
    "Paris": (48.8566, 2.3522),
    "Sydney": (-33.8688, 151.2093),
    "Dubai": (25.2048, 55.2708),
    "Singapore": (1.3521, 103.8198),
    "Mumbai": (19.0760, 72.8777),
    "São Paulo": (-23.5505, -46.6333),
    "Cairo": (30.0444, 31.2357),
}


class WeatherFetcher:
    """
    Fetch weather forecasts.
    Primary: NOAA api.weather.gov (US cities only)
    Fallback: OpenWeatherMap (international)
    """

    def __init__(self):
        self.noaa_base = settings.NOAA_API
        self.owm_key = settings.OPENWEATHERMAP_API_KEY
        self._noaa_headers = {
            "User-Agent": "(PolymarketWeatherBot, contact@example.com)",
            "Accept": "application/geo+json",
        }

    def fetch_forecast(self, city: str) -> Optional[dict]:
        """
        Get forecast for a city. Returns:
        {
            'city': str,
            'forecast_high_c': float,
            'forecast_high_f': float,
            'hourly_temps_c': [float, ...],
            'uncertainty_c': float,   # ± error margin
            'source': str,
        }
        """
        city_norm = normalize_city_name(city)
        coords = self._get_coords(city_norm)

        if coords is None:
            log.warning(f"[weather] Unknown city: {city_norm} — using OWM geocoding")
            return self._fetch_owm(city_norm)

        lat, lon = coords

        # Try NOAA first (US only: roughly lat 24-50, lon -125 to -66)
        if 24 <= lat <= 50 and -125 <= lon <= -66:
            result = self._fetch_noaa(city_norm, lat, lon)
            if result:
                return result
            log.warning(f"[weather] NOAA failed for {city_norm}, falling back to OWM")

        # Fallback to OWM
        return self._fetch_owm(city_norm, lat, lon)

    def _get_coords(self, city: str) -> Optional[tuple[float, float]]:
        """Look up city coordinates."""
        # Direct match
        if city in CITY_COORDS:
            return CITY_COORDS[city]

        # Fuzzy match (case-insensitive substring)
        city_lower = city.lower()
        for name, coords in CITY_COORDS.items():
            if city_lower in name.lower() or name.lower() in city_lower:
                return coords

        # Try OWM geocoding if we have a key
        if self.owm_key:
            return self._geocode_owm(city)

        return None

    @retry_with_backoff(max_retries=2, exceptions=(requests.RequestException,))
    def _fetch_noaa(self, city: str, lat: float, lon: float) -> Optional[dict]:
        """Fetch from NOAA api.weather.gov — US cities only."""
        try:
            # Step 1: Get grid point
            noaa_limiter.wait()
            point_url = f"{self.noaa_base}/points/{lat:.4f},{lon:.4f}"
            resp = requests.get(point_url, headers=self._noaa_headers, timeout=15)
            resp.raise_for_status()
            point_data = resp.json()

            forecast_url = point_data["properties"]["forecastHourly"]

            # Step 2: Get hourly forecast
            noaa_limiter.wait()
            resp = requests.get(forecast_url, headers=self._noaa_headers, timeout=15)
            resp.raise_for_status()
            hourly_data = resp.json()

            periods = hourly_data["properties"]["periods"]
            if not periods:
                return None

            # Extract next 24-48 hours of temperatures
            hourly_temps_f = [p["temperature"] for p in periods[:48]]
            hourly_temps_c = [fahrenheit_to_celsius(t) for t in hourly_temps_f]

            high_f = max(hourly_temps_f)
            high_c = max(hourly_temps_c)

            # NOAA doesn't give explicit uncertainty; use historical avg ≈ ±2°C
            uncertainty_c = 2.0

            result = {
                "city": city,
                "forecast_high_c": round(high_c, 1),
                "forecast_high_f": round(high_f, 1),
                "hourly_temps_c": [round(t, 1) for t in hourly_temps_c],
                "uncertainty_c": uncertainty_c,
                "source": "NOAA",
            }
            log.info(f"[weather] NOAA forecast for {city}: high={high_c:.1f}°C / {high_f:.1f}°F")
            return result

        except Exception as exc:
            log.error(f"[weather] NOAA fetch error for {city}: {exc}")
            return None

    def _fetch_owm(self, city: str, lat: float = None, lon: float = None) -> Optional[dict]:
        """Fetch from OpenWeatherMap — works internationally."""
        if not self.owm_key:
            log.warning("[weather] No OpenWeatherMap API key configured")
            return None

        try:
            if lat is not None and lon is not None:
                url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={self.owm_key}&units=metric"
            else:
                url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={self.owm_key}&units=metric"

            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            forecasts = data.get("list", [])
            if not forecasts:
                return None

            # Get next 48h of data (3-hour intervals → ~16 entries)
            hourly_temps_c = [f["main"]["temp_max"] for f in forecasts[:16]]
            high_c = max(hourly_temps_c)
            high_f = high_c * 9.0 / 5.0 + 32

            result = {
                "city": city,
                "forecast_high_c": round(high_c, 1),
                "forecast_high_f": round(high_f, 1),
                "hourly_temps_c": [round(t, 1) for t in hourly_temps_c],
                "uncertainty_c": 2.5,  # OWM typically slightly less precise
                "source": "OpenWeatherMap",
            }
            log.info(f"[weather] OWM forecast for {city}: high={high_c:.1f}°C")
            return result

        except Exception as exc:
            log.error(f"[weather] OWM fetch error for {city}: {exc}")
            return None

    def _geocode_owm(self, city: str) -> Optional[tuple[float, float]]:
        """Geocode a city name using OWM Geocoding API."""
        if not self.owm_key:
            return None
        try:
            url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={self.owm_key}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data:
                return (data[0]["lat"], data[0]["lon"])
        except Exception:
            pass
        return None
