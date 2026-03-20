"""Tests for src/exceptions.py — domain exception hierarchy."""

from src.exceptions import (
    SpendAnalysisError,
    AuthenticationError,
    ForbiddenError,
)


class TestAuthenticationError:
    def test_default_message(self):
        e = AuthenticationError()
        assert str(e) == "Authentication required"
        assert e.status_code == 401

    def test_custom_message(self):
        e = AuthenticationError("Token expired")
        assert str(e) == "Token expired"
        assert e.status_code == 401

    def test_is_spend_analysis_error(self):
        assert issubclass(AuthenticationError, SpendAnalysisError)


class TestForbiddenError:
    def test_default_message(self):
        e = ForbiddenError()
        assert str(e) == "Insufficient permissions"
        assert e.status_code == 403

    def test_custom_message(self):
        e = ForbiddenError("Admin access required")
        assert str(e) == "Admin access required"
        assert e.status_code == 403

    def test_is_spend_analysis_error(self):
        assert issubclass(ForbiddenError, SpendAnalysisError)
