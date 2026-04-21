from __future__ import annotations

from pathlib import Path
from typing import Any

from click.testing import CliRunner

from backend import cli as cli_module


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


class FakeClient:
    responses: list[FakeResponse] = []
    requests: list[tuple[str, dict[str, Any]]] = []
    base_url: str | None = None

    def __init__(self, base_url: str, timeout: float) -> None:
        self.__class__.base_url = base_url

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, path: str, json: dict[str, Any]) -> FakeResponse:
        self.__class__.requests.append((path, json))
        return self.__class__.responses.pop(0)


def setup_fake_client(monkeypatch: Any, responses: list[FakeResponse]) -> None:
    FakeClient.responses = responses
    FakeClient.requests = []
    FakeClient.base_url = None
    monkeypatch.setattr(cli_module.httpx, "Client", FakeClient)


def test_run_create_posts_memo_and_prints_run_id(monkeypatch: Any) -> None:
    setup_fake_client(monkeypatch, [FakeResponse(201, {"id": 7})])

    result = CliRunner().invoke(cli_module.cli, ["run", "create", "--memo", "CLI test"])

    assert result.exit_code == 0
    assert result.output == "7\n"
    assert FakeClient.base_url == "http://localhost:8000/api"
    assert FakeClient.requests == [("/runs", {"memo": "CLI test"})]


def test_analysis_save_posts_markdown_and_prints_success(monkeypatch: Any, tmp_path: Path) -> None:
    setup_fake_client(
        monkeypatch,
        [FakeResponse(201, {"ticker": "005930", "name": "Samsung", "judgment": "매수"})],
    )
    markdown_file = tmp_path / "analysis.md"
    markdown_file.write_text("analysis markdown", encoding="utf-8")

    result = CliRunner().invoke(
        cli_module.cli,
        [
            "analysis",
            "save",
            "--run-id",
            "1",
            "--ticker",
            "005930",
            "--name",
            "Samsung",
            "--model",
            "claude",
            "--file",
            str(markdown_file),
        ],
    )

    assert result.exit_code == 0
    assert result.output == "[OK] 005930 Samsung — 매수\n"
    assert FakeClient.requests[0][0] == "/analyses"
    assert FakeClient.requests[0][1] == {
        "run_id": 1,
        "ticker": "005930",
        "name": "Samsung",
        "model": "claude",
        "markdown": "analysis markdown",
        "judgment": "보류",
        "trend": "보류",
        "cloud_position": "보류",
        "ma_alignment": "보류",
    }


def test_analysis_save_prints_parse_failure(monkeypatch: Any, tmp_path: Path) -> None:
    setup_fake_client(
        monkeypatch,
        [FakeResponse(422, {"detail": "파싱 실패", "failed_fields": ["judgment"]})],
    )
    markdown_file = tmp_path / "analysis.md"
    markdown_file.write_text("invalid markdown", encoding="utf-8")

    result = CliRunner().invoke(
        cli_module.cli,
        [
            "analysis",
            "save",
            "--run-id",
            "1",
            "--ticker",
            "005930",
            "--name",
            "Samsung",
            "--model",
            "claude",
            "--file",
            str(markdown_file),
        ],
    )

    assert result.exit_code == 1
    assert result.output == "[FAIL] 005930 - 파싱 실패: ['judgment']\n"


def test_analysis_save_dir_uses_filename_metadata_and_prints_summary(monkeypatch: Any, tmp_path: Path) -> None:
    setup_fake_client(
        monkeypatch,
        [FakeResponse(201, {"ticker": "005930", "name": "Samsung", "judgment": "매수"})],
    )
    markdown_file = tmp_path / "005930_Samsung_weekly_20260421.md"
    markdown_file.write_text("analysis markdown", encoding="utf-8")

    result = CliRunner().invoke(
        cli_module.cli,
        ["analysis", "save-dir", "--run-id", "3", "--model", "claude", "--dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert result.output == "[OK] 005930 Samsung — 매수\n성공: 1개 / 실패: 0개 / Run ID: 3\n"
    assert FakeClient.requests[0][1]["ticker"] == "005930"
    assert FakeClient.requests[0][1]["name"] == "Samsung"


def test_parse_analysis_filename_allows_names_with_underscores() -> None:
    assert cli_module.parse_analysis_filename(Path("005930_Samsung_Electronics_weekly_20260421.md")) == (
        "005930",
        "Samsung_Electronics",
    )
