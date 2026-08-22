from app import update_checker


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_update_available(monkeypatch):
    monkeypatch.setattr(
        update_checker.requests, "get",
        lambda *args, **kwargs: FakeResponse(200, {
            "tag_name": "v9.0.0", "html_url": "https://example.test/release"
        }),
    )
    result = update_checker.check_for_updates()
    assert result.status == "update_available"
    assert result.latest_version == "9.0.0"
    assert result.release_url == "https://example.test/release"


def test_no_public_release_is_explained(monkeypatch):
    monkeypatch.setattr(
        update_checker.requests, "get", lambda *args, **kwargs: FakeResponse(404)
    )
    result = update_checker.check_for_updates()
    assert result.status == "no_release"
    assert "Release" in result.message


def test_update_check_never_follows_redirects(monkeypatch):
    observed = {}

    def fake_get(*args, **kwargs):
        observed.update(kwargs)
        return FakeResponse(200, {"tag_name": "v4.3.0"})

    monkeypatch.setattr(update_checker.requests, "get", fake_get)
    assert update_checker.check_for_updates().status == "up_to_date"
    assert observed["allow_redirects"] is False
