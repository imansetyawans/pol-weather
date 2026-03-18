"""
Edge Model — estimate probability that temperature exceeds threshold
using normal distribution and Monte Carlo simulation.
"""

import numpy as np
from scipy import stats
from typing import Optional
from utils.logger import log


class EdgeModel:
    """
    Estimate the probability that the actual highest temperature
    exceeds a given threshold, based on forecast data.

    Two methods:
      1. Normal distribution (fast, analytical)
      2. Monte Carlo simulation (more robust)
    """

    def __init__(self, monte_carlo_samples: int = 10_000):
        self.mc_samples = monte_carlo_samples

    def estimate_probability(
        self,
        forecast_high_c: float,
        threshold_c: float,
        uncertainty_c: float = 2.0,
    ) -> dict:
        """
        Estimate P(actual_high > threshold).

        Args:
            forecast_high_c: Forecasted high temperature (°C)
            threshold_c: Market threshold temperature (°C)
            uncertainty_c: Standard deviation of forecast error (°C)

        Returns:
            {
                'prob_exceeds': float,        # combined estimate
                'prob_normal': float,         # from normal distribution
                'prob_monte_carlo': float,    # from Monte Carlo
                'forecast_high_c': float,
                'threshold_c': float,
                'sigma': float,
            }
        """
        prob_normal = self._normal_distribution(forecast_high_c, threshold_c, uncertainty_c)
        prob_mc = self._monte_carlo(forecast_high_c, threshold_c, uncertainty_c)

        # Weighted average (60% normal, 40% MC) — normal is more stable
        prob_combined = 0.6 * prob_normal + 0.4 * prob_mc

        result = {
            "prob_exceeds": round(prob_combined, 4),
            "prob_normal": round(prob_normal, 4),
            "prob_monte_carlo": round(prob_mc, 4),
            "forecast_high_c": forecast_high_c,
            "threshold_c": threshold_c,
            "sigma": uncertainty_c,
        }

        log.debug(
            f"[edge_model] forecast={forecast_high_c}°C, threshold={threshold_c}°C, "
            f"σ={uncertainty_c}°C → P(exceed)={prob_combined:.4f} "
            f"(normal={prob_normal:.4f}, MC={prob_mc:.4f})"
        )
        return result

    def _normal_distribution(
        self, forecast: float, threshold: float, sigma: float
    ) -> float:
        """
        P(X > threshold) where X ~ N(forecast, sigma²)
        = 1 - Φ((threshold - forecast) / sigma)
        """
        if sigma <= 0:
            return 1.0 if forecast > threshold else 0.0

        z = (threshold - forecast) / sigma
        prob = 1.0 - stats.norm.cdf(z)
        return float(prob)

    def _monte_carlo(
        self, forecast: float, threshold: float, sigma: float
    ) -> float:
        """
        Monte Carlo simulation: sample N temperatures from N(forecast, sigma²)
        and count fraction exceeding threshold.
        """
        if sigma <= 0:
            return 1.0 if forecast > threshold else 0.0

        samples = np.random.normal(forecast, sigma, self.mc_samples)
        exceeds = np.sum(samples > threshold)
        prob = float(exceeds / self.mc_samples)
        return prob

    def estimate_with_hourly_data(
        self,
        hourly_temps_c: list[float],
        threshold_c: float,
        uncertainty_c: float = 2.0,
    ) -> dict:
        """
        Enhanced estimate using full hourly forecast data.
        Uses the max of hourly forecasts as mean and adjusts sigma
        based on the spread of hourly data.
        """
        if not hourly_temps_c:
            return self.estimate_probability(0, threshold_c, uncertainty_c)

        forecast_high = max(hourly_temps_c)

        # Adjust sigma: use max of forecast uncertainty and data spread
        data_spread = np.std(hourly_temps_c) if len(hourly_temps_c) > 1 else 0
        effective_sigma = max(uncertainty_c, data_spread * 0.5)

        return self.estimate_probability(forecast_high, threshold_c, effective_sigma)
