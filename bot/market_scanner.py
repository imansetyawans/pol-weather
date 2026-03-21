"""
Market Scanner — discover and filter weather temperature markets on Polymarket.
"""

import re
import json
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional
from utils.logger import log
from utils.helpers import retry_with_backoff, gamma_limiter, extract_temperature_threshold, parse_resolution_date
from config.settings import settings


class MarketScanner:
    """
    Scan the Gamma API for active weather-temperature markets,
    filter for 'Highest Temperature' events,
    and return the top N by volume.
    """

    def __init__(self):
        self.base_url = settings.GAMMA_HOST
        self._cached_markets: list[dict] = []

    @retry_with_backoff(max_retries=3, exceptions=(requests.RequestException, ValueError))
    def fetch_weather_events(self) -> list[dict]:
        """Fetch all active weather events from Gamma API."""
        all_events: list[dict] = []
        offset = 0
        limit = 100

        while True:
            gamma_limiter.wait()
            url = f"{self.base_url}/events"
            params = {
                "active": "true",
                "closed": "false",
                "tag_slug": "temperature",
                "limit": limit,
                "offset": offset,
            }
            log.debug(f"[scanner] Fetching events offset={offset}")
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if not data:
                break

            all_events.extend(data)
            offset += limit

            # Safety cap
            if offset >= 1000 or len(data) < limit:
                break

        log.info(f"[scanner] Fetched {len(all_events)} active temperature events")
        return all_events

    def filter_temperature_markets(self, events: list[dict]) -> list[dict]:
        """
        Filter events to only 'Highest Temperature' markets.
        Each event is a neg-risk multi-outcome with multiple temperature brackets.
        We return individual enriched market entries for each bracket.
        """
        filtered_events = []

        for event in events:
            title = event.get("title", "") or ""
            slug = event.get("slug", "") or ""

            # ── Must be a "Highest Temperature" market ──
            if not self._is_temperature_market(title, slug):
                continue

            # ── Must be a US city (NOAA available) ──
            city = self._extract_city_from_title(title)
            if not city or not self._is_us_city(city):
                continue

            filtered_events.append(event)

        log.info(f"[scanner] Found {len(filtered_events)} temperature events")

        # Now extract individual temperature bracket markets from each event
        all_markets = []
        for event in filtered_events:
            markets = event.get("markets", [])
            for market in markets:
                market_info = self._enrich_market(market, event)
                if market_info:
                    all_markets.append(market_info)

        log.info(f"[scanner] Extracted {len(all_markets)} individual temperature bracket markets")
        return all_markets

    def _is_temperature_market(self, title: str, slug: str) -> bool:
        """Check if event is a 'Highest Temperature' weather market."""
        combined = f"{title} {slug}".lower()
        return (
            "highest temperature" in combined
            or "highest-temperature" in combined
        )

    def _is_us_city(self, city: str) -> bool:
        """Check if city is likely in the US (supported by NOAA)."""
        from bot.weather_fetcher import CITY_COORDS
        city_lower = city.lower()
        for name, coords in CITY_COORDS.items():
            if city_lower in name.lower() or name.lower() in city_lower:
                lat, lon = coords
                # NOAA roughly covers lat 24-50, lon -125 to -66
                if 24 <= lat <= 50 and -125 <= lon <= -66:
                    return True
        return False

    def _enrich_market(self, market: dict, event: dict) -> Optional[dict]:
        """Extract and structure relevant market data from a Gamma API market."""
        question = market.get("question", "") or ""
        group_title = market.get("groupItemTitle", "") or ""

        # Extract city from event title (e.g., "Highest temperature in Shanghai on March 19?")
        city = self._extract_city_from_title(event.get("title", ""))

        # Extract temperature threshold from group item title or question
        threshold_c, threshold_f = self._extract_threshold(group_title, question)

        # Parse clobTokenIds — these come as a JSON string
        yes_token = None
        no_token = None
        clob_ids_raw = market.get("clobTokenIds", "")
        if isinstance(clob_ids_raw, str) and clob_ids_raw.startswith("["):
            try:
                clob_ids = json.loads(clob_ids_raw)
                if len(clob_ids) >= 2:
                    yes_token = clob_ids[0]
                    no_token = clob_ids[1]
            except (json.JSONDecodeError, IndexError):
                pass
        elif isinstance(clob_ids_raw, list) and len(clob_ids_raw) >= 2:
            yes_token = clob_ids_raw[0]
            no_token = clob_ids_raw[1]

        # Parse outcomePrices — also comes as a JSON string like '["0.68", "0.32"]'
        yes_price = None
        no_price = None
        prices_raw = market.get("outcomePrices", "")
        if isinstance(prices_raw, str) and prices_raw.startswith("["):
            try:
                prices = json.loads(prices_raw)
                if len(prices) >= 2:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
            except (json.JSONDecodeError, ValueError, IndexError):
                pass
        elif isinstance(prices_raw, str) and "," in prices_raw:
            parts = prices_raw.split(",")
            yes_price = self._safe_float(parts[0])
            no_price = self._safe_float(parts[1]) if len(parts) > 1 else None

        volume = self._safe_float(market.get("volume") or market.get("volumeNum") or 0)

        return {
            "condition_id": market.get("conditionId") or market.get("condition_id"),
            "question_id": market.get("questionID") or market.get("question_id"),
            "question": question,
            "group_title": group_title,
            "slug": market.get("slug", ""),
            "event_slug": event.get("slug", ""),
            "event_title": event.get("title", ""),
            "city": city,
            "threshold_c": threshold_c,
            "threshold_f": threshold_f,
            "yes_token_id": yes_token,
            "no_token_id": no_token,
            "yes_price": yes_price,
            "no_price": no_price,
            "volume": volume,
            "event_volume": self._safe_float(event.get("volume") or event.get("volume24hr") or 0),
            "end_date": market.get("endDate") or event.get("endDate"),
            "neg_risk": event.get("negRisk", True),
            "tick_size": str(market.get("orderPriceMinTickSize") or market.get("minimum_tick_size") or "0.001"),
            "min_order_size": market.get("orderMinSize", 5),
            "active": market.get("active", True),
        }

    def _extract_city_from_title(self, title: str) -> Optional[str]:
        """Extract city name from event title like 'Highest temperature in Shanghai on March 19?'"""
        match = re.search(
            r"temperature\s+in\s+(.+?)\s+on\s+",
            title,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        # Fallback: "temperature in <CITY>"
        match2 = re.search(r"temperature\s+in\s+(.+?)[\?\.]?\s*$", title, re.IGNORECASE)
        if match2:
            return match2.group(1).strip()
        return None

    def _extract_threshold(self, group_title: str, question: str) -> tuple[Optional[float], Optional[float]]:
        """
        Extract temperature threshold from groupItemTitle or question.
        Examples:
            "12°C" → (12.0, 53.6)
            "4°C or below" → (4.0, 39.2)
            "86-87°F" → (None, 86.5)  → converted to Celsius
            "18°C or higher" → (18.0, 64.4)
        """
        combined = f"{group_title} {question}"

        # Match single Celsius: "12°C" or "12 C" or "be 12°C"
        match_c = re.search(r"(\d+)\s*°?\s*C(?:\s|$|,|\?|or)", combined)
        if match_c:
            c_val = float(match_c.group(1))
            return (c_val, c_val * 9 / 5 + 32)

        # Match range Fahrenheit: "86-87°F"
        match_f_range = re.search(r"(\d+)-(\d+)\s*°?\s*F", combined)
        if match_f_range:
            f_low = float(match_f_range.group(1))
            f_high = float(match_f_range.group(2))
            f_mid = (f_low + f_high) / 2
            return ((f_mid - 32) * 5 / 9, f_mid)

        # Match single Fahrenheit: "86°F"
        match_f = re.search(r"(\d+)\s*°?\s*F(?:\s|$|,|\?|or)", combined)
        if match_f:
            f_val = float(match_f.group(1))
            return ((f_val - 32) * 5 / 9, f_val)

        # Match bare number from groupItemTitle
        bare_match = re.search(r"^(\d+)", group_title.strip())
        if bare_match:
            val = float(bare_match.group(1))
            # Heuristic: < 60 likely Celsius, else Fahrenheit
            if val < 60:
                return (val, val * 9 / 5 + 32)
            else:
                return ((val - 32) * 5 / 9, val)

        return (None, None)

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert a value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def scan(self, limit_top: bool = True) -> list[dict]:
        """
        Main entry point:
        1. Fetch all active weather temperature events.
        2. Filter out non-US cities or bad dates.
        3. Sort by volume and optionally pick the top N.
        4. Extract the nested markets for those events.
        """
        try:
            log.info("Fetching active weather events from Polymarket Gamma API...")
            all_events = self.fetch_weather_events()
            if not all_events:
                return []

            # Filter events for temperature and valid dates
            weather_events = self.filter_temperature_markets(all_events)
            log.info(f" Found {len(weather_events)} temperature events")

            if not weather_events:
                return []

            # Group markets by event slug, sort events by total volume
            event_groups: dict[str, list[dict]] = {}
            event_volumes: dict[str, float] = {}
            for m in weather_events: # weather_events here are already individual markets
                slug = m.get("event_slug", "unknown")
                if slug not in event_groups:
                    event_groups[slug] = []
                    event_volumes[slug] = m.get("event_volume", 0) or 0
                event_groups[slug].append(m)

            # Sort events by volume (descending)
            sorted_slugs = sorted(event_volumes.keys(), key=lambda s: event_volumes[s], reverse=True)
            top_slugs = set(sorted_slugs[: settings.TOP_MARKETS])

            # Select top N events or all events based on limit_top
            target_slugs = sorted_slugs[: settings.TOP_MARKETS] if limit_top else sorted_slugs

            # Collect all markets from target events
            target_markets = []
            target_cities = set()
            for slug in target_slugs:
                for market in event_groups[slug]:
                    city = market.get("city", "")
                    if city:
                        target_cities.add(city)
                    market["is_top_market"] = (slug in top_slugs)
                    target_markets.append(market)

            self._cached_markets = target_markets
            
            if limit_top:
                log.info(f" Selected top {settings.TOP_MARKETS} events ({len(target_markets)} bracket markets) for cities: {', '.join(target_cities)}")
            else:
                log.info(f" Selected all {len(target_slugs)} events ({len(target_markets)} bracket markets) for cities: {', '.join(target_cities)}")
            
            return target_markets

        except Exception as exc:
            log.error(f"[scanner] Scan failed: {exc}")
            return self._cached_markets

    def get_cached_markets(self) -> list[dict]:
        """Return the most recent scan results."""
        return self._cached_markets
