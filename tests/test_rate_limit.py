"""Tests for rate limiting decorator in api_helpers."""

import time

from src.api_helpers import rate_limit, _rate_limit_buckets


class _MockRequest:
    def __init__(self, ip="1.2.3.4", method="POST"):
        self.headers = {"X-Forwarded-For": ip}
        self.method = method


class _MockResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.headers = {}


class TestRateLimit:
    def setup_method(self):
        _rate_limit_buckets.clear()

    def test_allows_requests_under_limit(self):
        @rate_limit(requests=5, window=60)
        def endpoint(req):
            return _MockResponse(200)

        req = _MockRequest()
        for _ in range(5):
            resp = endpoint(req)
            assert resp.status_code == 200

    def test_blocks_requests_over_limit(self):
        @rate_limit(requests=3, window=60)
        def endpoint(req):
            return _MockResponse(200)

        req = _MockRequest()
        for _ in range(3):
            endpoint(req)
        resp = endpoint(req)
        assert resp.status_code == 429

    def test_returns_retry_after_header(self):
        @rate_limit(requests=1, window=60)
        def endpoint(req):
            return _MockResponse(200)

        req = _MockRequest()
        endpoint(req)
        resp = endpoint(req)
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_different_ips_tracked_separately(self):
        @rate_limit(requests=2, window=60)
        def endpoint(req):
            return _MockResponse(200)

        req_a = _MockRequest(ip="1.1.1.1")
        req_b = _MockRequest(ip="2.2.2.2")
        endpoint(req_a)
        endpoint(req_a)
        resp_a = endpoint(req_a)
        resp_b = endpoint(req_b)
        assert resp_a.status_code == 429
        assert resp_b.status_code == 200

    def test_window_expires(self):
        @rate_limit(requests=1, window=1)
        def endpoint(req):
            return _MockResponse(200)

        req = _MockRequest()
        endpoint(req)
        resp = endpoint(req)
        assert resp.status_code == 429
        time.sleep(1.1)
        resp = endpoint(req)
        assert resp.status_code == 200

    def test_bypasses_options(self):
        @rate_limit(requests=1, window=60)
        def endpoint(req):
            return _MockResponse(200)

        req = _MockRequest(method="OPTIONS")
        # Should not count against limit
        resp = endpoint(req)
        assert resp.status_code == 200
        resp = endpoint(req)
        assert resp.status_code == 200
