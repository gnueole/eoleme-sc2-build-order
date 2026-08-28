"""
Tests du service HTTP : validation des paramètres, plafond de taille, et
comportement face à un fichier qui n'est pas un replay.
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
        # Le fichier reste invalide : on doit dépasser la validation et échouer
        # sur le parsing, pas sur le format du repère de temps.
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
