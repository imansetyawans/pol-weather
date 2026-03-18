"""
Shared utilities — retry decorator, rate limiter, temperature conversion, parsing.
"""

import re
import time
import functools
from typing import Any, Callable, Optional
from utils.logger import log


# ── Retry with exponential backoff ──

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
):
    """Decorator – retry a function with exponential backoff on failure."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        log.warning(
                            f"[retry] {func.__name__} attempt {attempt + 1}/{max_retries} "
                            f"failed: {exc}  — retrying in {delay:.1f}s"
                        )
                        time.sleep(delay)
            raise last_exc  # type: ignore

        return wrapper
    return decorator


# ── Rate limiter ──

class RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, calls_per_second: float = 2.0):
        self.min_interval = 1.0 / calls_per_second
        self._last_call = 0.0

    def wait(self):
        now = time.time()
        elapsed = now - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.time()


# Global rate limiters
noaa_limiter = RateLimiter(calls_per_second=1.0)
gamma_limiter = RateLimiter(calls_per_second=5.0)


# ── Temperature conversion ──

def fahrenheit_to_celsius(f: float) -> float:
    return (f - 32) * 5.0 / 9.0


def celsius_to_fahrenheit(c: float) -> float:
    return c * 9.0 / 5.0 + 32


# ── Market question parsing ──

def extract_temperature_threshold(question: str) -> Optional[dict]:
    """
    Parse a market title like:
      'Highest temperature in Shanghai on March 19, 2026'
      'Will the highest temperature in New York exceed 30°C on ...'
      'Highest temperature in Shanghai exceeds 30°C'

    Returns: { 'city': str, 'threshold_c': float | None, 'threshold_f': float | None }
    """
    result: dict = {"city": None, "threshold_c": None, "threshold_f": None, "raw": question}

    # Try to extract city — "temperature in <CITY> on" or "temperature in <CITY>"
    city_match = re.search(
        r"temperature\s+in\s+(.+?)(?:\s+on\s+|\s+exceed|\s+above|\s+below|\s*$)",
        question,
        re.IGNORECASE,
    )
    if city_match:
        result["city"] = city_match.group(1).strip().rstrip("?.,")

    # Try to extract threshold with unit
    temp_match = re.search(r"(\d+\.?\d*)\s*°?\s*(C|F|celsius|fahrenheit)", question, re.IGNORECASE)
    if temp_match:
        value = float(temp_match.group(1))
        unit = temp_match.group(2).upper()
        if unit in ("C", "CELSIUS"):
            result["threshold_c"] = value
            result["threshold_f"] = celsius_to_fahrenheit(value)
        else:
            result["threshold_f"] = value
            result["threshold_c"] = fahrenheit_to_celsius(value)

    # Try bare number if no unit specified (e.g., "exceeds 85")
    if result["threshold_c"] is None and result["threshold_f"] is None:
        bare_match = re.search(r"exceed[s]?\s+(\d+\.?\d*)", question, re.IGNORECASE)
        if bare_match:
            value = float(bare_match.group(1))
            # Heuristic: if > 50, likely Fahrenheit; else Celsius
            if value > 50:
                result["threshold_f"] = value
                result["threshold_c"] = fahrenheit_to_celsius(value)
            else:
                result["threshold_c"] = value
                result["threshold_f"] = celsius_to_fahrenheit(value)

    return result


def normalize_city_name(city: str) -> str:
    """Normalize city name for geocoding lookups."""
    # Remove common suffixes / noise
    city = re.sub(r"\s*\(.+?\)", "", city)
    city = city.strip().title()
    return city


def parse_resolution_date(title: str) -> Optional[str]:
    """
    Extract a date string from a market title.
    e.g. 'March 19, 2026' or 'march-19-2026'
    """
    # "on March 19, 2026"
    date_match = re.search(
        r"on\s+(\w+\s+\d{1,2},?\s*\d{4})", title, re.IGNORECASE
    )
    if date_match:
        return date_match.group(1).strip()

    # slug style: "march-19-2026"
    slug_match = re.search(
        r"(\w+)-(\d{1,2})-(\d{4})", title, re.IGNORECASE
    )
    if slug_match:
        month, day, year = slug_match.groups()
        return f"{month.title()} {day}, {year}"

    return None
