"""Tests for cost config loader."""
from __future__ import annotations

from middleware.cost_config import load_config


class TestLoadConfig:
    def test_loads_baseline_settings(self) -> None:
        cfg = load_config()
        assert cfg["baselines"]["bootstrap_count"] == 20
        assert cfg["baselines"]["anomaly_stddev"] == 2.0

    def test_loads_model_costs(self) -> None:
        cfg = load_config()
        assert "gpt-5.4-mini" in cfg["model_costs"]
        assert cfg["model_costs"]["gpt-5.4-mini"]["input_per_1k"] == 0.00015

    def test_loads_quality_threshold(self) -> None:
        cfg = load_config()
        assert cfg["quality"]["min_score"] == 7.0

    def test_calculates_cost(self) -> None:
        from middleware.cost_config import calculate_cost
        cost = calculate_cost("gpt-5.4-mini", input_tokens=1000, output_tokens=500)
        expected = 1000 * 0.00015 / 1000 + 500 * 0.0006 / 1000
        assert abs(cost - expected) < 1e-10

    def test_local_model_zero_cost(self) -> None:
        from middleware.cost_config import calculate_cost
        cost = calculate_cost("qwen3.5:9b", input_tokens=1000, output_tokens=500)
        assert cost == 0.0

    def test_unknown_model_zero_cost(self) -> None:
        from middleware.cost_config import calculate_cost
        cost = calculate_cost("unknown-model", input_tokens=1000, output_tokens=500)
        assert cost == 0.0
