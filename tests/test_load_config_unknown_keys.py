"""load_config must ignore unknown config keys (forward/backward compat)."""

from __future__ import annotations

from trading_pulse.agent import dryrun_agent as da


def test_load_config_ignores_unknown_keys(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        '{"initial_capital": 1234, "strategy_mode": "balanced_mix", '
        '"not_a_real_field": true, "method2_max_offers": 3}',
        encoding="utf-8",
    )
    monkeypatch.setattr(da, "CONFIG_FILE", cfg_path)
    monkeypatch.setattr(
        "trading_pulse.core.env_config.apply_secrets_to_config",
        lambda raw: raw,
    )
    cfg = da.load_config()
    assert cfg.initial_capital == 1234
    assert cfg.strategy_mode == "balanced_mix"
    assert cfg.method2_max_offers == 3
    assert not hasattr(cfg, "not_a_real_field")
