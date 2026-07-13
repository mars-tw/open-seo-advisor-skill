import pytest

from seo_advisor.indexnow.key import (
    InvalidIndexNowKeyError,
    generate_key,
    validate_key_format,
)


class TestGenerateKey:
    def test_generates_key_with_valid_format(self):
        key = generate_key()
        validate_key_format(key)  # 不拋例外即通過

    def test_generates_unique_keys(self):
        assert generate_key() != generate_key()

    def test_generated_key_length_within_protocol_bounds(self):
        key = generate_key()
        assert 8 <= len(key) <= 128


class TestValidateKeyFormat:
    def test_accepts_alnum_key(self):
        validate_key_format("abc12345")

    def test_accepts_key_with_hyphen(self):
        validate_key_format("abc-12345-xyz")

    def test_rejects_too_short_key(self):
        with pytest.raises(InvalidIndexNowKeyError):
            validate_key_format("abc123")

    def test_rejects_too_long_key(self):
        with pytest.raises(InvalidIndexNowKeyError):
            validate_key_format("a" * 129)

    def test_rejects_key_with_invalid_characters(self):
        with pytest.raises(InvalidIndexNowKeyError):
            validate_key_format("abc_123!@#")

    def test_rejects_key_with_whitespace(self):
        with pytest.raises(InvalidIndexNowKeyError):
            validate_key_format("abc 12345")

    def test_rejects_empty_key(self):
        with pytest.raises(InvalidIndexNowKeyError):
            validate_key_format("")
