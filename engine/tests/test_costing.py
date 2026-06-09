"""Offline unit tests for modules/costing.py — no network, no API spend."""
import pytest

from modules.costing import (
    image_unit_cost, model_price, estimate_run_cost,
    BudgetTracker, BudgetExceeded, RateLimiter,
)

CFG = {
    "available_models": {
        "image_generators": [
            {"id": "gpt-image-2", "config_key": "gpt_image", "usd_per_image": 0.17},
            {"id": "gemini-image", "config_key": "gemini_image", "usd_per_image": 0.04},
            {"id": "nano-banana-pro", "config_key": "gemini_image", "usd_per_image": 0.08},
        ],
        "parsers": [
            {"id": "gemini-2.5-pro", "usd_per_million_input_tokens": 1.25,
             "usd_per_million_output_tokens": 10.0},
            {"id": "anthropic/claude-sonnet-4", "usd_per_million_input_tokens": 3.0,
             "usd_per_million_output_tokens": 15.0},
        ],
    }
}


# ── image_unit_cost ──────────────────────────────────────────────────────────
def test_image_unit_cost_by_id():
    assert image_unit_cost(CFG, "gpt-image-2") == 0.17
    assert image_unit_cost(CFG, "nano-banana-pro") == 0.08  # id wins over shared key


def test_image_unit_cost_by_config_key_first_match():
    assert image_unit_cost(CFG, "", "gpt_image") == 0.17
    assert image_unit_cost(CFG, "", "gemini_image") == 0.04  # first generator wins


def test_image_unit_cost_gemini_api_key_alias():
    # runtime injection renames gemini_image -> gemini_api_key; pricing must still resolve
    assert image_unit_cost(CFG, "", "gemini_api_key") == 0.04


def test_image_unit_cost_unknown_is_zero():
    assert image_unit_cost(CFG, "nope", "nope") == 0.0
    assert image_unit_cost({}, "gpt-image-2") == 0.0


# ── model_price ──────────────────────────────────────────────────────────────
def test_model_price_prefix_tolerant():
    assert model_price(CFG, "gemini-2.5-pro")["in"] == 1.25
    assert model_price(CFG, "anthropic/claude-sonnet-4")["out"] == 15.0
    assert model_price(CFG, "claude-sonnet-4")["out"] == 15.0  # bare id of a prefixed entry
    assert model_price(CFG, "totally-unknown") == {"in": 0.0, "out": 0.0}


# ── estimate_run_cost ────────────────────────────────────────────────────────
def test_estimate_scales_with_scenes():
    e1 = estimate_run_cost(CFG, 4, 1, 3, image_id="gpt-image-2",
                           parser_model="gemini-2.5-pro", critic_model="gemini-2.5-pro")
    e2 = estimate_run_cost(CFG, 8, 1, 3, image_id="gpt-image-2",
                           parser_model="gemini-2.5-pro", critic_model="gemini-2.5-pro")
    assert e2["total_typical"] > e1["total_typical"]
    assert e2["images_max"] == 2 * e1["images_max"]


def test_estimate_image_count_and_cost_math():
    e = estimate_run_cost(CFG, 5, 1, 3, image_id="gpt-image-2")
    assert e["images_typical"] == 10   # min(2,3) attempts * 5 scenes
    assert e["images_max"] == 15       # 3 retries * 5 scenes
    assert e["image_cost_typical"] == pytest.approx(10 * 0.17, rel=1e-9)
    assert e["image_cost_max"] == pytest.approx(15 * 0.17, rel=1e-9)
    assert e["total_max"] >= e["total_typical"]


def test_estimate_supplementary_visuals_counted():
    # images_per_scene=2 adds one auto-pass supplementary image per scene
    e = estimate_run_cost(CFG, 3, 2, 2, image_id="gpt-image-2")
    # per scene: 1 supplementary + min(2,2)=2 key attempts = 3 typical; *3 scenes = 9
    assert e["images_typical"] == 9


def test_estimate_zero_scenes_is_free():
    e = estimate_run_cost(CFG, 0, 1, 3, image_id="gpt-image-2")
    assert e["images_typical"] == 0
    assert e["total_typical"] == 0.0


def test_estimate_more_retries_raises_ceiling_not_typical():
    lo = estimate_run_cost(CFG, 5, 1, 2, image_id="gpt-image-2")
    hi = estimate_run_cost(CFG, 5, 1, 5, image_id="gpt-image-2")
    assert hi["images_max"] > lo["images_max"]
    assert hi["images_typical"] == lo["images_typical"]  # typical caps at 2 attempts


# ── BudgetTracker ────────────────────────────────────────────────────────────
def test_budget_under_then_over():
    bt = BudgetTracker(1.0)
    bt.add(0.5)
    bt.check()                      # under ceiling -> no raise
    assert bt.spent == 0.5
    bt.add(0.6)                     # now 1.1
    with pytest.raises(BudgetExceeded):
        bt.check()


def test_budget_zero_ceiling_never_raises():
    bt = BudgetTracker(0.0)
    bt.add(10_000.0)
    bt.check()                      # no ceiling -> never raises
    assert bt.would_exceed(1e12) is False


def test_budget_would_exceed():
    bt = BudgetTracker(1.0)
    bt.add(0.8)
    assert bt.would_exceed(0.3) is True
    assert bt.would_exceed(0.1) is False


def test_budget_thread_safe_accumulation():
    import threading
    bt = BudgetTracker(0.0)

    def worker():
        for _ in range(1000):
            bt.add(0.001)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert bt.spent == pytest.approx(8 * 1000 * 0.001, rel=1e-6)


# ── RateLimiter (deterministic, injected clock + sleep) ──────────────────────
def _fake_clock_sleep():
    state = {"t": 100.0}          # non-zero origin, like time.monotonic()
    slept = []

    def clock():
        return state["t"]

    def sleep(s):
        slept.append(s)
        state["t"] += s           # advancing the clock models real sleeping

    return clock, sleep, slept, state


def test_rate_limiter_first_call_no_wait_then_spaces():
    clock, sleep, slept, _ = _fake_clock_sleep()
    rl = RateLimiter(1.5, _clock=clock, _sleep=sleep)
    rl.wait()                      # first call -> no sleep
    assert slept == []
    rl.wait()                      # immediately again -> must space by 1.5
    assert len(slept) == 1 and slept[0] == pytest.approx(1.5)


def test_rate_limiter_respects_elapsed_time():
    clock, sleep, slept, state = _fake_clock_sleep()
    rl = RateLimiter(1.5, _clock=clock, _sleep=sleep)
    rl.wait()
    state["t"] += 1.0              # 1.0s already elapsed naturally
    rl.wait()                      # only needs to wait the remaining 0.5
    assert slept[0] == pytest.approx(0.5)


def test_rate_limiter_disabled_when_interval_zero():
    slept = []
    rl = RateLimiter(0.0, _clock=lambda: 0.0, _sleep=lambda s: slept.append(s))
    rl.wait()
    rl.wait()
    assert slept == []
