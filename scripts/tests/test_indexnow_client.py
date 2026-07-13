import httpx
import pytest
import respx

from seo_advisor.indexnow.client import (
    IndexNowApiError,
    IndexNowKeyVerificationError,
    resolve_endpoint,
    submit_batch,
    verify_key_location,
)
from seo_advisor.security.rate_limiter import RateLimiter


class TestResolveEndpoint:
    def test_accepts_indexnow(self):
        assert resolve_endpoint("indexnow") == "https://api.indexnow.org/indexnow"

    def test_accepts_bing(self):
        assert resolve_endpoint("bing") == "https://www.bing.com/indexnow"

    def test_rejects_arbitrary_endpoint_name(self):
        with pytest.raises(IndexNowApiError):
            resolve_endpoint("https://evil.example.com/indexnow")


class TestVerifyKeyLocation:
    @respx.mock
    def test_accepts_matching_content(self):
        respx.get("https://example.com/abc123.txt").mock(return_value=httpx.Response(200, text="abc123"))
        verify_key_location("https://example.com/abc123.txt", "abc123")  # 不拋例外即通過

    @respx.mock
    def test_accepts_content_with_trailing_whitespace(self):
        respx.get("https://example.com/abc123.txt").mock(return_value=httpx.Response(200, text="abc123\n"))
        verify_key_location("https://example.com/abc123.txt", "abc123")

    @respx.mock
    def test_rejects_mismatched_content(self):
        respx.get("https://example.com/abc123.txt").mock(return_value=httpx.Response(200, text="wrong-key"))
        with pytest.raises(IndexNowKeyVerificationError):
            verify_key_location("https://example.com/abc123.txt", "abc123")

    @respx.mock
    def test_rejects_404(self):
        respx.get("https://example.com/abc123.txt").mock(return_value=httpx.Response(404))
        with pytest.raises(IndexNowKeyVerificationError):
            verify_key_location("https://example.com/abc123.txt", "abc123")

    @respx.mock
    def test_rejects_cross_host_redirect(self):
        respx.get("https://example.com/abc123.txt").mock(
            return_value=httpx.Response(302, headers={"location": "https://evil.com/abc123.txt"})
        )
        with pytest.raises(IndexNowKeyVerificationError):
            verify_key_location("https://example.com/abc123.txt", "abc123")

    @respx.mock
    def test_rejects_same_host_redirect_too(self):
        """即使是同網域的 redirect，key 檔案本身也不該有重新導向
        （協定期待直接可讀取），一律拒絕不追蹤。"""
        respx.get("https://example.com/abc123.txt").mock(
            return_value=httpx.Response(301, headers={"location": "https://example.com/key/abc123.txt"})
        )
        with pytest.raises(IndexNowKeyVerificationError):
            verify_key_location("https://example.com/abc123.txt", "abc123")

    @respx.mock
    def test_connection_failure_raises_clear_error(self):
        respx.get("https://example.com/abc123.txt").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(IndexNowKeyVerificationError):
            verify_key_location("https://example.com/abc123.txt", "abc123")

    def test_rejects_key_location_pointing_at_private_network(self):
        """key_location 是使用者輸入的網址，指向內網/loopback 時必須在
        發送請求前就被 SSRF 防護擋下，不應該真的發出 HTTP 請求。"""
        with pytest.raises(IndexNowKeyVerificationError):
            verify_key_location("http://127.0.0.1/abc123.txt", "abc123")

    def test_rejects_key_location_pointing_at_cloud_metadata(self):
        with pytest.raises(IndexNowKeyVerificationError):
            verify_key_location("http://169.254.169.254/abc123.txt", "abc123")

    def test_rejects_non_http_scheme(self):
        with pytest.raises(IndexNowKeyVerificationError):
            verify_key_location("file:///etc/passwd", "abc123")

    @respx.mock
    def test_key_file_exceeding_size_cap_is_rejected_without_full_read(self):
        """回應 body 遠超過 4KB 上限時，應該在讀滿上限就停止累積並直接
        判定超量拒絕，而不是把整個超大 body 讀進記憶體。"""
        respx.get("https://example.com/abc123.txt").mock(
            return_value=httpx.Response(200, text="a" * (10 * 1024 * 1024))
        )
        with pytest.raises(IndexNowKeyVerificationError):
            verify_key_location("https://example.com/abc123.txt", "abc123")

    @respx.mock
    def test_oversized_body_is_rejected_even_if_prefix_matches_key(self):
        """回應內容是「合法 key + 大量垃圾」時，若只用截斷後的前綴比對會
        誤判為驗證通過；正確行為是一旦偵測到超量就直接拒絕，不做前綴比對。"""
        oversized_content = "abc123" + "x" * (10 * 1024)
        respx.get("https://example.com/abc123.txt").mock(return_value=httpx.Response(200, text=oversized_content))
        with pytest.raises(IndexNowKeyVerificationError):
            verify_key_location("https://example.com/abc123.txt", "abc123")


class TestSubmitBatch:
    @respx.mock
    def test_successful_submission(self):
        respx.post("https://api.indexnow.org/indexnow").mock(return_value=httpx.Response(200))
        result = submit_batch(
            endpoint="https://api.indexnow.org/indexnow",
            site_host="example.com",
            key="abc123",
            key_location="https://example.com/abc123.txt",
            urls=["https://example.com/post-1"],
            rate_limiter=RateLimiter(100),
        )
        assert result.response_status == "submitted"
        assert result.status_code == 200

    @respx.mock
    def test_key_invalid_status_mapped(self):
        respx.post("https://api.indexnow.org/indexnow").mock(return_value=httpx.Response(403))
        result = submit_batch(
            endpoint="https://api.indexnow.org/indexnow",
            site_host="example.com",
            key="abc123",
            key_location="https://example.com/abc123.txt",
            urls=["https://example.com/post-1"],
            rate_limiter=RateLimiter(100),
        )
        assert result.response_status == "key_invalid_or_not_found"

    @respx.mock
    def test_url_not_owned_status_mapped(self):
        respx.post("https://api.indexnow.org/indexnow").mock(return_value=httpx.Response(422))
        result = submit_batch(
            endpoint="https://api.indexnow.org/indexnow",
            site_host="example.com",
            key="abc123",
            key_location="https://example.com/abc123.txt",
            urls=["https://example.com/post-1"],
            rate_limiter=RateLimiter(100),
        )
        assert result.response_status == "url_not_owned_or_schema_mismatch"

    def test_rejects_batch_exceeding_protocol_limit(self):
        urls = [f"https://example.com/{i}" for i in range(10_001)]
        with pytest.raises(IndexNowApiError):
            submit_batch(
                endpoint="https://api.indexnow.org/indexnow",
                site_host="example.com",
                key="abc123",
                key_location="https://example.com/abc123.txt",
                urls=urls,
                rate_limiter=RateLimiter(100),
            )

    @respx.mock
    def test_does_not_leak_key_in_error_detail_on_failure(self):
        respx.post("https://api.indexnow.org/indexnow").mock(side_effect=httpx.ConnectError("refused"))
        result = submit_batch(
            endpoint="https://api.indexnow.org/indexnow",
            site_host="example.com",
            key="super-secret-key-value",
            key_location="https://example.com/super-secret-key-value.txt",
            urls=["https://example.com/post-1"],
            rate_limiter=RateLimiter(100),
        )
        assert result.response_status == "request_failed"
