from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import httpx


DEFAULT_API_BASE_URL = "http://localhost:8000/api"
PLACEHOLDER_PARSED_FIELDS = {
    "judgment": "보류",
    "trend": "보류",
    "cloud_position": "보류",
    "ma_alignment": "보류",
}


@click.group()
@click.option(
    "--api-base-url",
    default=DEFAULT_API_BASE_URL,
    show_default=True,
    help="Backend API base URL.",
)
@click.pass_context
def cli(ctx: click.Context, api_base_url: str) -> None:
    ctx.obj = {"api_base_url": api_base_url.rstrip("/")}


@cli.group("run")
def run_group() -> None:
    pass


@run_group.command("create")
@click.option("--memo", default=None, help="Optional run memo.")
@click.pass_context
def create_run(ctx: click.Context, memo: str | None) -> None:
    response = _post_json(ctx.obj["api_base_url"], "/runs", {"memo": memo})
    if response.status_code != 201:
        _echo_failure("run", response)
        raise click.exceptions.Exit(1)

    click.echo(response.json()["id"])


@cli.group("analysis")
def analysis_group() -> None:
    pass


@analysis_group.command("save")
@click.option("--run-id", type=int, required=True)
@click.option("--ticker", required=True)
@click.option("--name", required=True)
@click.option("--model", "model_name", required=True)
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.pass_context
def save_analysis(
    ctx: click.Context,
    run_id: int,
    ticker: str,
    name: str,
    model_name: str,
    file_path: Path,
) -> None:
    success = _save_analysis_file(
        api_base_url=ctx.obj["api_base_url"],
        run_id=run_id,
        ticker=ticker,
        name=name,
        model_name=model_name,
        file_path=file_path,
    )
    if not success:
        raise click.exceptions.Exit(1)


@analysis_group.command("save-dir")
@click.option("--run-id", type=int, required=True)
@click.option("--model", "model_name", required=True)
@click.option("--dir", "dir_path", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.pass_context
def save_analysis_dir(ctx: click.Context, run_id: int, model_name: str, dir_path: Path) -> None:
    markdown_files = sorted(dir_path.glob("*.md"))
    success_count = 0
    failure_count = 0

    for file_path in markdown_files:
        try:
            ticker, name = parse_analysis_filename(file_path)
        except ValueError as exc:
            click.echo(f"[FAIL] {file_path.name} - {exc}")
            failure_count += 1
            continue

        if _save_analysis_file(
            api_base_url=ctx.obj["api_base_url"],
            run_id=run_id,
            ticker=ticker,
            name=name,
            model_name=model_name,
            file_path=file_path,
        ):
            success_count += 1
        else:
            failure_count += 1

    click.echo(f"성공: {success_count}개 / 실패: {failure_count}개 / Run ID: {run_id}")
    if failure_count:
        raise click.exceptions.Exit(1)


def parse_analysis_filename(file_path: Path) -> tuple[str, str]:
    stem = file_path.stem
    parts = stem.split("_")
    if len(parts) < 2:
        raise ValueError("파일명에서 ticker/name 추출 실패")

    ticker = parts[0].strip()
    if not ticker:
        raise ValueError("파일명에서 ticker 추출 실패")

    if len(parts) >= 4 and parts[-2] == "weekly" and parts[-1].isdigit():
        name_parts = parts[1:-2]
    else:
        name_parts = parts[1:]

    name = "_".join(name_parts).strip()
    if not name:
        raise ValueError("파일명에서 name 추출 실패")

    return ticker, name


def _save_analysis_file(
    *,
    api_base_url: str,
    run_id: int,
    ticker: str,
    name: str,
    model_name: str,
    file_path: Path,
) -> bool:
    markdown = file_path.read_text(encoding="utf-8")
    payload = {
        "run_id": run_id,
        "ticker": ticker,
        "name": name,
        "model": model_name,
        "markdown": markdown,
        **PLACEHOLDER_PARSED_FIELDS,
    }

    response = _post_json(api_base_url, "/analyses", payload)
    if response.status_code == 201:
        body = response.json()
        click.echo(f"[OK] {body['ticker']} {body['name']} — {body['judgment']}")
        return True

    _echo_failure(ticker, response)
    return False


def _post_json(api_base_url: str, path: str, payload: dict[str, Any]) -> httpx.Response:
    try:
        with httpx.Client(base_url=api_base_url, timeout=10.0) as client:
            return client.post(path, json=payload)
    except httpx.RequestError as exc:
        raise click.ClickException(f"API 요청 실패: {exc}") from exc


def _echo_failure(label: str, response: httpx.Response) -> None:
    try:
        body = response.json()
    except ValueError:
        body = {}

    failed_fields = body.get("failed_fields")
    if failed_fields:
        click.echo(f"[FAIL] {label} - 파싱 실패: {failed_fields}")
        return

    detail = body.get("detail", response.text)
    click.echo(f"[FAIL] {label} - {response.status_code}: {detail}")


if __name__ == "__main__":
    cli()
