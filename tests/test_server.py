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


class TestPromptEndpoint:
    def test_serves_the_real_prompt_not_a_summary(self, client):
        # The page shows this text verbatim; a restated summary would drift.
        body = client.get("/api/prompt?lang=fr").json()
        assert body["lang"] == "fr"
        assert "Analyse comme un coach" in body["prompt"]
        assert "⚡" in body["prompt"]

    def test_follows_the_requested_language(self, client):
        assert "Coach me on it" in client.get("/api/prompt?lang=en").json()["prompt"]

    def test_unknown_language_falls_back_to_french(self, client):
        body = client.get("/api/prompt?lang=de").json()
        assert body["lang"] == "fr"

    def test_the_trailing_separator_is_trimmed(self, client):
        # The prompt ends with a --- rule before the report; on its own it should
        # not trail blank lines into the tooltip.
        assert client.get("/api/prompt").json()["prompt"].endswith("---")


class TestHiddenUtility:
    def test_the_hidden_class_beats_component_display(self, client):
        # .overlay sets display:flex later in the sheet; without !important the
        # about dialog opens on page load.
        css = client.get("/css/styles.css").text
        assert ".hidden { display: none !important; }" in css

    def test_the_dialog_starts_hidden_in_the_markup(self, client):
        page = client.get("/").text
        assert 'class="overlay hidden" id="about"' in page
        assert 'class="prompt-box hidden" id="prompt-preview"' in page


class TestInterfaceDictionary:
    """
    The page reads its labels from translations.js by key. A key removed on one
    side, or renamed without updating the markup, shows the raw key to the user
    and nothing else complains.
    """

    def catalogues(self, client):
        import re
        js = client.get("/js/translations.js").text
        fr = set(re.findall(r'^\s{4}([a-z_]+):', js.split("en: {")[0], re.M))
        en = set(re.findall(r'^\s{4}([a-z_]+):', js.split("en: {")[1], re.M))
        return fr, en

    def test_both_languages_carry_the_same_keys(self, client):
        fr, en = self.catalogues(client)
        assert fr == en, f"écart : {sorted(fr ^ en)}"

    def test_every_key_the_markup_asks_for_exists(self, client):
        import re
        html = client.get("/").text
        used = set(re.findall(r'data-i18n(?:-placeholder|-aria|-title)?="([a-z_]+)"', html))
        fr, _ = self.catalogues(client)
        assert used, "aucune clé trouvée dans le HTML — l'extraction est cassée"
        assert not (used - fr), f"absentes du dictionnaire : {sorted(used - fr)}"

    def test_every_key_the_script_asks_for_exists(self, client):
        import re
        app = client.get("/js/app.js").text
        used = set(re.findall(r'\bt\("([a-z_]+)"', app))
        # Ces deux-là passent par une variable, pas par un littéral.
        used |= {"copied_short", "copy_failed_short"}
        fr, _ = self.catalogues(client)
        assert not (used - fr), f"absentes du dictionnaire : {sorted(used - fr)}"


class TestCopyButtons:
    def test_the_markdown_can_be_copied_from_the_head_and_the_foot(self, client):
        page = client.get("/").text
        assert 'id="copy-top"' in page
        assert 'id="copy"' in page

    def test_both_carry_the_same_label_key(self, client):
        import re
        page = client.get("/").text
        labels = re.findall(r'id="copy(?:-top)?" data-i18n="([a-z_]+)"', page)
        assert labels == ["btn_copy", "btn_copy"], labels


class TestHealthLogNoise:
    def make_record(self, message):
        import logging
        return logging.LogRecord("uvicorn.access", logging.INFO, "", 0, message, None, None)

    def test_the_health_check_is_kept_out_of_the_logs(self):
        f = server.DropHealthAccessLogs()
        assert f.filter(self.make_record('127.0.0.1:5 - "GET /api/health HTTP/1.1" 200 OK')) is False

    def test_every_other_request_still_gets_logged(self):
        f = server.DropHealthAccessLogs()
        for line in ['1.2.3.4:5 - "POST /api/extract HTTP/1.1" 200 OK',
                     '1.2.3.4:5 - "GET / HTTP/1.1" 200 OK',
                     '1.2.3.4:5 - "GET /icons/btn-unit-terran-marine.webp HTTP/1.1" 200 OK']:
            assert f.filter(self.make_record(line)) is True, line

    def test_the_filter_is_attached_to_the_access_logger(self):
        import logging
        filters = logging.getLogger("uvicorn.access").filters
        assert any(isinstance(f, server.DropHealthAccessLogs) for f in filters)
