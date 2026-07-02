import time

from seo_advisor.security.rate_limiter import RateLimiter


def test_first_call_does_not_wait():
    limiter = RateLimiter(requests_per_second=2)
    start = time.monotonic()
    limiter.wait()
    assert time.monotonic() - start < 0.05


def test_second_call_waits_minimum_interval():
    limiter = RateLimiter(requests_per_second=10)  # min interval = 0.1s
    limiter.wait()
    start = time.monotonic()
    limiter.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.08  # 留一點誤差空間


def test_zero_rate_disables_limiting():
    limiter = RateLimiter(requests_per_second=0)
    start = time.monotonic()
    limiter.wait()
    limiter.wait()
    assert time.monotonic() - start < 0.05
