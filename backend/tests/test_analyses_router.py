from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.crud import create_analysis, create_run
from backend.database import Base, get_db
from backend.routers.analyses import router
from backend.schemas import AnalysisCreate


VALID_MARKDOWN = """
## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 정배열

### 4. 매매 판정
**매수**

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | 20주선 지지 확인 | 75,000원 |
| 1차 목표 | 전고점 재도전 | 82,000 |
| 손절 기준 | 추세 이탈 | 71,500원 |
"""


INVALID_PRICE_MARKDOWN = """
## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 혼조

### 4. 매매 판정
**홀드**

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 눌림 진입 | 1차 지지선 부근 조정 확인 | 1,659원 |
| 돌파 진입 | 1차 저항 주봉 종가 돌파 확인 | 1,998원 |
| 1차 목표 | 2차 저항 도달 | 1,963원 |
| 손절 기준 | 2차 지지 이탈 | 1,626원 |
"""


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(router)

    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(client: TestClient) -> Generator[Session, None, None]:
    override = client.app.dependency_overrides[get_db]
    session = next(override())
    try:
        yield session
    finally:
        session.close()


def page_items(response: Response) -> list[dict[str, object]]:
    return response.json()["items"]


def test_create_analysis_returns_201_with_parsed_fields(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, memo="analysis run")

    response = client.post(
        "/api/analyses",
        json={
            "run_id": run.id,
            "ticker": "005930",
            "name": "Samsung Electronics",
            "model": "gpt-5.4",
            "markdown": VALID_MARKDOWN,
            "judgment": "보류",
            "trend": "보류",
            "cloud_position": "보류",
            "ma_alignment": "보류",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["run_id"] == run.id
    assert body["judgment"] == "매수"
    assert body["trend"] == "상승"
    assert body["cloud_position"] == "구름 위"
    assert body["ma_alignment"] == "정배열"
    assert body["entry_price"] == 75000.0


def test_create_analysis_returns_422_when_required_fields_are_missing(
    client: TestClient, db_session: Session
) -> None:
    run = create_run(db_session, memo="invalid analysis run")

    response = client.post(
        "/api/analyses",
        json={
            "run_id": run.id,
            "ticker": "005930",
            "name": "Samsung Electronics",
            "model": "gpt-5.4",
            "markdown": "### 1. 현재 구조 요약\n- 추세: 상승",
            "judgment": "보류",
            "trend": "보류",
            "cloud_position": "보류",
            "ma_alignment": "보류",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "파싱 실패"
    assert set(body["failed_fields"]) == {"judgment", "cloud_position", "ma_alignment"}


def test_create_analysis_returns_422_when_price_scenario_is_inconsistent(
    client: TestClient, db_session: Session
) -> None:
    run = create_run(db_session, memo="invalid price analysis run")

    response = client.post(
        "/api/analyses",
        json={
            "run_id": run.id,
            "ticker": "291650",
            "name": "압타머사이언스",
            "model": "gpt-5.4",
            "markdown": INVALID_PRICE_MARKDOWN,
            "judgment": "보류",
            "trend": "보류",
            "cloud_position": "보류",
            "ma_alignment": "보류",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "파싱 실패"
    assert body["failed_fields"] == ["price_consistency"]


def test_list_analyses_by_run_filters_by_judgment(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, memo="filter analyses")

    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="000660",
            name="SK Hynix",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매도",
            trend="하락",
            cloud_position="구름 아래",
            ma_alignment="역배열",
        ),
    )

    response = client.get(f"/api/runs/{run.id}/analyses", params={"judgment": "매수"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["judgment"] == "매수"


def test_create_analysis_returns_404_when_run_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/analyses",
        json={
            "run_id": 99999,
            "ticker": "005930",
            "name": "Samsung Electronics",
            "model": "gpt-5.4",
            "markdown": VALID_MARKDOWN,
            "judgment": "보류",
            "trend": "보류",
            "cloud_position": "보류",
            "ma_alignment": "보류",
        },
    )

    assert response.status_code == 404


def test_list_analyses_returns_404_when_run_not_found(client: TestClient) -> None:
    response = client.get("/api/runs/99999/analyses")

    assert response.status_code == 404


def test_list_analyses_returns_all_when_no_filter(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, memo="no filter test")
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="000660",
            name="SK Hynix",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매도",
            trend="하락",
            cloud_position="구름 아래",
            ma_alignment="역배열",
        ),
    )

    response = client.get(f"/api/runs/{run.id}/analyses")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_all_analyses_returns_newest_first(client: TestClient, db_session: Session) -> None:
    first_run = create_run(db_session, memo="global list 1")
    second_run = create_run(db_session, memo="global list 2")

    older = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="홀드",
            trend="횡보",
            cloud_position="구름 안",
            ma_alignment="혼조",
        ),
    )
    newer = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=second_run.id,
            ticker="000660",
            name="SK Hynix",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )

    response = client.get("/api/analyses")

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 25
    assert body["total"] == 2
    assert body["total_pages"] == 1
    assert [item["id"] for item in body["items"]] == [newer.id, older.id]


def test_list_all_analyses_paginates_with_metadata(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, memo="global pagination")
    first = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="홀드",
            trend="횡보",
            cloud_position="구름 안",
            ma_alignment="혼조",
        ),
    )
    second = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="000660",
            name="SK Hynix",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    third = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="035420",
            name="NAVER",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매도",
            trend="하락",
            cloud_position="구름 아래",
            ma_alignment="역배열",
        ),
    )

    first_page = client.get("/api/analyses", params={"page": 1, "page_size": 2})
    second_page = client.get("/api/analyses", params={"page": 2, "page_size": 2})

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert first_page.json()["total_pages"] == 2
    assert [item["id"] for item in page_items(first_page)] == [third.id, second.id]
    assert second_page.status_code == 200
    assert [item["id"] for item in page_items(second_page)] == [first.id]


def test_list_all_analyses_filters_by_judgment(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, memo="global judgment filter")
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="000660",
            name="SK Hynix",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매도",
            trend="하락",
            cloud_position="구름 아래",
            ma_alignment="역배열",
        ),
    )

    response = client.get("/api/analyses", params={"judgment": "매수"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["judgment"] == "매수"


def test_list_all_analyses_filters_by_run_id(client: TestClient, db_session: Session) -> None:
    first_run = create_run(db_session, memo="global run filter 1")
    second_run = create_run(db_session, memo="global run filter 2")
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    selected = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=second_run.id,
            ticker="000660",
            name="SK Hynix",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매도",
            trend="하락",
            cloud_position="구름 아래",
            ma_alignment="역배열",
        ),
    )

    response = client.get("/api/analyses", params={"run_id": second_run.id})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [selected.id]


def test_list_all_analyses_filters_by_ticker_or_name(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, memo="global query filter")
    samsung = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="005930",
            name="삼성전자",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="000660",
            name="SK Hynix",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매도",
            trend="하락",
            cloud_position="구름 아래",
            ma_alignment="역배열",
        ),
    )

    ticker_response = client.get("/api/analyses", params={"q": "593"})
    name_response = client.get("/api/analyses", params={"q": "삼성"})

    assert ticker_response.status_code == 200
    assert [item["id"] for item in page_items(ticker_response)] == [samsung.id]
    assert name_response.status_code == 200
    assert [item["id"] for item in page_items(name_response)] == [samsung.id]


def test_list_all_analyses_returns_422_for_invalid_judgment(client: TestClient) -> None:
    response = client.get("/api/analyses", params={"judgment": "잘못된값"})

    assert response.status_code == 422


def test_list_all_analyses_returns_422_for_invalid_pagination(client: TestClient) -> None:
    invalid_page = client.get("/api/analyses", params={"page": 0})
    invalid_page_size = client.get("/api/analyses", params={"page_size": 101})

    assert invalid_page.status_code == 422
    assert invalid_page_size.status_code == 422


def test_list_all_analyses_filters_by_judgment_and_run_id(client: TestClient, db_session: Session) -> None:
    first_run = create_run(db_session, memo="combined filter 1")
    second_run = create_run(db_session, memo="combined filter 2")
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=second_run.id,
            ticker="000660",
            name="SK Hynix",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=second_run.id,
            ticker="035420",
            name="NAVER",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매도",
            trend="하락",
            cloud_position="구름 아래",
            ma_alignment="역배열",
        ),
    )

    response = client.get("/api/analyses", params={"judgment": "매수", "run_id": second_run.id})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["judgment"] == "매수"
    assert body["items"][0]["ticker"] == "000660"

    response = client.get(
        "/api/analyses",
        params={"judgment": "매수", "run_id": second_run.id, "q": "000"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["ticker"] == "000660"


def test_list_analyses_returns_422_for_invalid_judgment(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, memo="invalid judgment test")
    response = client.get(f"/api/runs/{run.id}/analyses", params={"judgment": "잘못된값"})

    assert response.status_code == 422


def test_get_analysis_history_returns_same_ticker_newest_first(
    client: TestClient, db_session: Session
) -> None:
    first_run = create_run(db_session, memo="history 1")
    second_run = create_run(db_session, memo="history 2")

    older = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="홀드",
            trend="횡보",
            cloud_position="구름 안",
            ma_alignment="혼조",
        ),
    )
    newer = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=second_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )

    response = client.get(f"/api/analyses/{older.id}/history")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [newer.id, older.id]


def test_get_analysis_returns_analysis_detail(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, memo="detail run")
    analysis = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown=VALID_MARKDOWN,
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )

    response = client.get(f"/api/analyses/{analysis.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == analysis.id
    assert body["ticker"] == "005930"
    assert body["markdown"] == VALID_MARKDOWN


def test_get_analysis_returns_404_when_not_found(client: TestClient) -> None:
    response = client.get("/api/analyses/99999")

    assert response.status_code == 404


def test_get_analysis_history_returns_404_when_not_found(client: TestClient) -> None:
    response = client.get("/api/analyses/99999/history")

    assert response.status_code == 404
