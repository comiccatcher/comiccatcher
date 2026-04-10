import pytest
import httpx
from comiccatcher.api.client import APIClient
from comiccatcher.models.feed import FeedProfile

def test_discover_auth_document_url_link_header():
    profile = FeedProfile(id="test", name="test", url="http://example.com/opds")
    client = APIClient(profile)
    
    # Mock response with Link header
    response = httpx.Response(
        401,
        headers={"Link": '<http://example.com/auth.json>; rel="http://opds-spec.org/auth/document"'},
        request=httpx.Request("GET", "http://example.com/opds")
    )
    
    auth_url = client.discover_auth_document_url(response)
    assert auth_url == "http://example.com/auth.json"

def test_discover_auth_document_url_link_header_authenticate():
    profile = FeedProfile(id="test", name="test", url="http://example.com/opds")
    client = APIClient(profile)
    
    # Mock response with rel="authenticate"
    response = httpx.Response(
        401,
        headers={"Link": '<auth.json>; rel="authenticate"'},
        request=httpx.Request("GET", "http://example.com/opds")
    )
    
    auth_url = client.discover_auth_document_url(response)
    assert auth_url == "http://example.com/auth.json"

def test_discover_auth_document_url_body_content_type():
    profile = FeedProfile(id="test", name="test", url="http://example.com/opds")
    client = APIClient(profile)
    
    # Mock response where the body IS the auth doc
    response = httpx.Response(
        401,
        headers={"Content-Type": "application/opds-authentication+json"},
        content='{"authentication": []}',
        request=httpx.Request("GET", "http://example.com/auth.json")
    )
    
    auth_url = client.discover_auth_document_url(response)
    assert auth_url == "http://example.com/auth.json"

def test_discover_auth_document_url_no_auth():
    profile = FeedProfile(id="test", name="test", url="http://example.com/opds")
    client = APIClient(profile)
    
    # Normal 401 without OPDS auth metadata
    response = httpx.Response(
        401,
        request=httpx.Request("GET", "http://example.com/opds")
    )
    
    auth_url = client.discover_auth_document_url(response)
    assert auth_url is None
