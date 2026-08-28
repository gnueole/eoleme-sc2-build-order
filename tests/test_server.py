"""
Tests for the HTTP service: parameter validation, size cap, and behaviour when
handed a file that is not a replay.
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import server


@pytest.fixture
def client():
    return TestClient(server.app)


def upload(client, content=b"pas un replay", **fields):
    return client.post(
        "/api/extract",
        files={"replay": ("partie.SC2Replay", io.BytesIO(content), "application/octet-stream")},
        data=fields,
    )


class TestHealth:
    def test_reports_ok_and_limits(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["max_upload_mb"] >= 1


class TestValidation:
    def test_rejects_unknown_format(self, client):
        assert upload(client, format="csv").status_code == 400

    def test_rejects_unknown_workers_mode(self, client):
        assert upload(client, workers="beaucoup").status_code == 400

    def test_rejects_malformed_cutoff(self, client):
        response = upload(client, cutoff="huit heures")
        assert response.status_code == 400
        assert "MM:SS" in response.json()["detail"]

    def test_accepts_a_well_formed_cutoff(self, client):
        # The file stays invalid: we must get past validation and fail on the
        # parse, not on the time marker's format.
        assert upload(client, cutoff="8:00").status_code == 422

    def test_rejects_empty_file(self, client):
        assert upload(client, content=b"").status_code == 400


class TestLimits:
    def test_rejects_a_file_over_the_cap(self, client, monkeypatch):
        monkeypatch.setattr(server, "MAX_UPLOAD_BYTES", 1024)
        response = upload(client, content=b"x" * 4096)
        assert response.status_code == 413
        assert "Mo" in response.json()["detail"]


class TestGarbageInput:
    def test_explains_rather_than_crashing(self, client):
        response = upload(client, content=b"ceci n'est pas une archive MPQ")
        assert response.status_code == 422
        assert "replay" in response.json()["detail"].lower()


class TestUsageCounter:
    def test_crosses_the_threshold_once_only(self, monkeypatch):
        monkeypatch.setattr(server, "FEEDBACK_THRESHOLD", 3)
        server._usage.update(day="", count=0, announced=False)
        assert [server.record_usage() for _ in range(5)] == [False, False, True, False, False]

    def test_resets_on_a_new_day(self, monkeypatch):
        monkeypatch.setattr(server, "FEEDBACK_THRESHOLD", 2)
        server._usage.update(day="1999-01-01", count=99, announced=True)
        assert server.record_usage() is False   # nouveau jour : compteur remis à 1
        assert server._usage["count"] == 1


class TestStaticSite:
    def test_serves_the_page(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "Build Order Forge" in response.text


class TestLanguageNegotiation:
    def test_errors_answer_in_english_when_asked(self, client):
        response = upload(client, lang="en", format="csv")
        assert response.status_code == 400
        assert "Unknown value" in response.json()["detail"]

    def test_errors_answer_in_french_by_default(self, client):
        response = upload(client, format="csv")
        assert "inconnue" in response.json()["detail"]

    def test_unreadable_file_is_explained_in_english(self, client):
        response = upload(client, lang="en", content=b"not a replay at all")
        assert response.status_code == 422
        assert "StarCraft II replay" in response.json()["detail"]

    def test_unknown_language_falls_back_to_french_rather_than_failing(self, client):
        response = upload(client, lang="de", format="csv")
        assert response.status_code == 400
        assert "inconnue" in response.json()["detail"]

    def test_size_cap_message_follows_the_language(self, client, monkeypatch):
        monkeypatch.setattr(server, "MAX_UPLOAD_BYTES", 1024)
        assert "MB" in upload(client, lang="en", content=b"x" * 4096).json()["detail"]
        assert "Mo" in upload(client, lang="fr", content=b"x" * 4096).json()["detail"]


class TestStaticAssets:
    def test_serves_the_stylesheet(self, client):
        response = client.get("/css/styles.css")
        assert response.status_code == 200
        assert "--accent-color" in response.text

    def test_serves_the_translations(self, client):
        response = client.get("/js/translations.js")
        assert response.status_code == 200
        assert "TRANSLATIONS" in response.text


class TestIconAssets:
    def test_icons_are_served_as_webp_not_octet_stream(self, client):
        # StaticFiles trusts Python's mimetypes table, which does not know .webp
        # on every base image. An octet-stream image caches badly.
        response = client.get("/icons/btn-unit-terran-marine.webp")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"

    def test_a_missing_icon_is_a_404_not_a_crash(self, client):
        assert client.get("/icons/btn-nope.webp").status_code == 404
