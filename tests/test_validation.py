"""Tests for src/validation.py — input sanitization."""

import pytest

from src.validation import safe_resource_id
from src.exceptions import ValidationError


class TestSafeResourceId:
    def test_valid_simple_id(self):
        assert safe_resource_id("naval-wartsila") == "naval-wartsila"

    def test_valid_uuid(self):
        assert (
            safe_resource_id("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
            == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        )

    def test_strips_whitespace(self):
        assert safe_resource_id("  naval  ") == "naval"

    def test_rejects_empty(self):
        with pytest.raises(ValidationError):
            safe_resource_id("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValidationError):
            safe_resource_id("   ")

    def test_rejects_none(self):
        with pytest.raises(ValidationError):
            safe_resource_id(None)

    def test_rejects_dot_dot(self):
        with pytest.raises(ValidationError):
            safe_resource_id("../secrets")

    def test_rejects_dot_dot_in_middle(self):
        with pytest.raises(ValidationError):
            safe_resource_id("project/../secrets")

    def test_rejects_forward_slash(self):
        with pytest.raises(ValidationError):
            safe_resource_id("project/subdir")

    def test_rejects_backslash(self):
        with pytest.raises(ValidationError):
            safe_resource_id("project\\subdir")

    def test_rejects_null_byte(self):
        with pytest.raises(ValidationError):
            safe_resource_id("project\x00evil")

    def test_rejects_oversized_input(self):
        with pytest.raises(ValidationError):
            safe_resource_id("a" * 257)

    def test_custom_field_name_in_error(self):
        with pytest.raises(ValidationError, match="jobId"):
            safe_resource_id("", field="jobId")

    def test_allows_dots_without_traversal(self):
        assert safe_resource_id("v1.0") == "v1.0"

    def test_allows_underscores(self):
        assert safe_resource_id("my_project_123") == "my_project_123"

    def test_max_length_boundary(self):
        assert safe_resource_id("a" * 256) == "a" * 256
