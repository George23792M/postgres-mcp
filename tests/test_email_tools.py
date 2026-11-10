"""Tests for email template tool."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.tools.email_tools import get_active_email_template


@pytest.mark.asyncio
async def test_get_active_email_template_found(monkeypatch):
    """Test successful retrieval of an active email template."""
    from app.repositories import email_repository
    from app.tools import email_tools
    
    mock_pool = MagicMock()
    expected_template = {
        "active": True,
        "subject": "Welcome!",
        "html_body": "<p>Welcome to our service</p>",
    }
    
    async def mock_active_template(pool, template_name):
        if template_name == "welcome":
            return expected_template
        return None
    
    # Mock get_pool in the email_tools module (where it's imported) and the repository function
    monkeypatch.setattr(email_tools, "get_pool", MagicMock(return_value=mock_pool))
    monkeypatch.setattr(email_repository, "active_email_template", mock_active_template)
    
    result = await get_active_email_template("welcome")
    assert result == {"found": True, "template": expected_template}


@pytest.mark.asyncio
async def test_get_active_email_template_not_found(monkeypatch):
    """Test retrieval when template does not exist."""
    from app.repositories import email_repository
    from app.tools import email_tools
    
    mock_pool = MagicMock()
    
    async def mock_active_template(pool, template_name):
        return None
    
    # Mock get_pool in the email_tools module (where it's imported) and the repository function
    monkeypatch.setattr(email_tools, "get_pool", MagicMock(return_value=mock_pool))
    monkeypatch.setattr(email_repository, "active_email_template", mock_active_template)
    
    result = await get_active_email_template("nonexistent")
    assert result == {"found": False}


@pytest.mark.asyncio
async def test_get_active_email_template_parameter_validation():
    """Test that template_name parameter is validated."""
    # Test with empty string should fail validation
    with pytest.raises(Exception):  # Will raise validation error
        await get_active_email_template("")


@pytest.mark.asyncio 
async def test_get_active_email_template_parameter_max_length():
    """Test that template_name respects max length."""
    # Template name longer than 100 chars should fail
    long_name = "x" * 101
    with pytest.raises(Exception):  # Will raise validation error
        await get_active_email_template(long_name)
