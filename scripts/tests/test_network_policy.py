from seo_advisor.security.network_policy import is_private_or_blocked_host


def test_loopback_ip_is_blocked():
    assert is_private_or_blocked_host("127.0.0.1") is True


def test_private_ipv4_is_blocked():
    assert is_private_or_blocked_host("192.168.1.1") is True
    assert is_private_or_blocked_host("10.0.0.5") is True
    assert is_private_or_blocked_host("172.16.0.1") is True


def test_localhost_hostname_is_blocked():
    assert is_private_or_blocked_host("localhost") is True


def test_cloud_metadata_ip_is_blocked():
    assert is_private_or_blocked_host("169.254.169.254") is True


def test_public_ip_is_not_blocked():
    assert is_private_or_blocked_host("8.8.8.8") is False


def test_unresolvable_hostname_is_not_blocked():
    # DNS 解析失敗時應 fail open，讓後續連線嘗試自然失敗，而非誤擋合法網址
    assert is_private_or_blocked_host("this-domain-should-not-exist-xyz123.invalid") is False
