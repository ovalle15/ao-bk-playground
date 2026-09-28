"""API contract tests with no dependency on NASA's live service."""

import json
from datetime import date, timedelta
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from .conftest import get


def api_get(base_url, path):
    status, headers, body = get(base_url + path)
    assert headers.get_content_type() == "application/json"
    return status, json.loads(body)


@pytest.mark.parametrize(
    "invalid_date",
    ["not-a-date", "1995-06-15", "2024-02-30", "2024-1-1"],
)
def test_invalid_dates_are_rejected_before_calling_nasa(api_server, nasa_stub, invalid_date):
    state, _url = nasa_stub
    status, payload = api_get(api_server, "/api/nasaimage?date=" + quote(invalid_date))

    assert status == 400
    assert payload == {"success": False, "error": "Date must be between 1995-06-16 and today"}
    assert state["requests"] == []


def test_future_date_is_rejected(api_server, nasa_stub):
    state, _url = nasa_stub
    future = (date.today() + timedelta(days=1)).isoformat()

    status, _payload = api_get(api_server, "/api/nasaimage?date=" + future)

    assert status == 400
    assert state["requests"] == []


def test_image_response_is_normalized_and_date_is_forwarded(api_server, nasa_stub):
    state, _url = nasa_stub
    state["body"] = {
        "title": "A galaxy", "date": "2024-01-01", "explanation": "Spiral arms",
        "copyright": "A. Astronomer", "media_type": "image",
        "url": "https://images.example/standard.jpg", "hdurl": "https://images.example/large.jpg",
    }

    status, payload = api_get(api_server, "/api/nasaimage?date=2024-01-01")

    assert status == 200
    assert payload == {"success": True, "item": {
        "title": "A galaxy", "date": "2024-01-01", "explanation": "Spiral arms",
        "attribution": "A. Astronomer", "mediaType": "image",
        "mediaUrl": "https://images.example/standard.jpg",
        "imageUrl": "https://images.example/standard.jpg",
        "hdImageUrl": "https://images.example/large.jpg",
    }}
    request = urlsplit(state["requests"][0])
    assert request.path == "/apod"
    assert parse_qs(request.query) == {
        "api_key": ["pytest-token"], "thumbs": ["true"], "date": ["2024-01-01"]
    }


def test_video_response_uses_thumbnail_and_defaults(api_server, nasa_stub):
    state, _url = nasa_stub
    state["body"] = {
        "title": "A launch", "date": "2024-01-02", "explanation": "A video",
        "media_type": "video", "url": "https://video.example/watch",
        "thumbnail_url": "https://images.example/thumb.jpg",
    }

    status, payload = api_get(api_server, "/api/nasaimage")

    assert status == 200
    assert payload["item"]["attribution"] == "NASA"
    assert payload["item"]["mediaType"] == "video"
    assert payload["item"]["mediaUrl"] == "https://video.example/watch"
    assert payload["item"]["imageUrl"] == "https://images.example/thumb.jpg"
    assert payload["item"]["hdImageUrl"] == "https://video.example/watch"
    assert parse_qs(urlsplit(state["requests"][0]).query) == {
        "api_key": ["pytest-token"], "thumbs": ["true"]
    }


def test_upstream_failure_returns_safe_gateway_error(api_server, nasa_stub):
    state, _url = nasa_stub
    state["status"] = 503
    state["body"] = {"error": "upstream details should not be exposed"}

    status, payload = api_get(api_server, "/api/nasaimage?date=2024-01-01")

    assert status == 502
    assert payload == {"success": False, "error": "Unable to fetch the NASA image"}
    assert len(state["requests"]) == 1
