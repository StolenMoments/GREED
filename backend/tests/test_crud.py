from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.crud import (
    calc_entry_gap_pct,
    create_analysis,
    create_run,
    create_job,
    get_analyses,
    get_analyses_by_run,
    get_analyses_page,
    get_analysis,
    get_analysis_history,
    get_job,
    get_run,
    get_runs,
    update_job_done,
    update_job_failed,
    upsert_stock_price,
)
from backend.database import Base
from backend.korean_search import extract_korean_initials, is_korean_initial_query
from backend.schemas import AnalysisCreate
from backend.timezone import seoul_now


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_create_run_persists_run(db_session: Session) -> None:
    run = create_run(db_session, memo="first run")

    assert run.id is not None
    assert run.memo == "first run"
    assert run.analysis_count == 0
    assert get_run(db_session, run.id) is not None


def test_create_run_uses_seoul_time(db_session: Session) -> None:
    run = create_run(db_session, memo="seoul time")

    now_in_seoul = seoul_now().replace(tzinfo=None)
    assert abs(now_in_seoul - run.created_at.replace(tzinfo=None)) < timedelta(seconds=5)


def test_get_runs_includes_analysis_count(db_session: Session) -> None:
    first_run = create_run(db_session, memo="first")
    second_run = create_run(db_session, memo="second")

    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt",
            markdown="analysis one",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
            entry_price=70000,
            target_price=76000,
            stop_loss=66000,
        ),
    )
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="000660",
            name="SK Hynix",
            model="gpt",
            markdown="analysis two",
            judgment="보유",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )

    runs = get_runs(db_session)

    assert [run.id for run in runs] == [second_run.id, first_run.id]
    run_counts = {run.id: run.analysis_count for run in runs}
    assert run_counts[first_run.id] == 2
    assert run_counts[second_run.id] == 0


def test_get_analyses_by_run_filters_by_judgment(db_session: Session) -> None:
    run = create_run(db_session, memo="filter target")

    buy_analysis = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="claude",
            markdown="buy markdown",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    hold_analysis = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="000660",
            name="SK Hynix",
            model="claude",
            markdown="hold markdown",
            judgment="보유",
            trend="횡보",
            cloud_position="구름 속",
            ma_alignment="혼조",
        ),
    )

    all_analyses = get_analyses_by_run(db_session, run.id)
    buy_analyses = get_analyses_by_run(db_session, run.id, judgment="매수")

    assert [analysis.id for analysis in all_analyses] == [hold_analysis.id, buy_analysis.id]
    assert [analysis.id for analysis in buy_analyses] == [buy_analysis.id]


def test_get_analyses_filters_by_ticker_or_name(db_session: Session) -> None:
    run = create_run(db_session, memo="query filter")

    samsung = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="005930",
            name="삼성전자",
            model="claude",
            markdown="samsung markdown",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    hynix = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="000660",
            name="SK Hynix",
            model="claude",
            markdown="hynix markdown",
            judgment="보유",
            trend="횡보",
            cloud_position="구름 속",
            ma_alignment="혼조",
        ),
    )

    ticker_matches = get_analyses(db_session, q="593")
    name_matches = get_analyses(db_session, q="삼성")
    blank_query_matches = get_analyses(db_session, q="   ")

    assert [analysis.id for analysis in ticker_matches] == [samsung.id]
    assert [analysis.id for analysis in name_matches] == [samsung.id]
    assert [analysis.id for analysis in blank_query_matches] == [hynix.id, samsung.id]


def test_extract_korean_initials() -> None:
    assert extract_korean_initials("피제이메탈") == "ㅍㅈㅇㅁㅌ"
    assert extract_korean_initials("삼성전자") == "ㅅㅅㅈㅈ"
    assert extract_korean_initials("SK Hynix 005930") == ""
    assert is_korean_initial_query("ㅈㅇㅁ")
    assert not is_korean_initial_query("ㅈㅇㅁ메")


def test_get_analyses_filters_by_korean_initials(db_session: Session) -> None:
    run = create_run(db_session, memo="initial query filter")

    pjmetal = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="128660",
            name="피제이메탈",
            model="claude",
            markdown="pjmetal markdown",
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
            ticker="005930",
            name="삼성전자",
            model="claude",
            markdown="samsung markdown",
            judgment="보유",
            trend="횡보",
            cloud_position="구름 속",
            ma_alignment="혼조",
        ),
    )

    prefix_matches = get_analyses(db_session, q="ㅍㅈㅇ")
    middle_matches = get_analyses(db_session, q="ㅈㅇㅁ")
    suffix_matches = get_analyses(db_session, q="ㅇㅁㅌ")
    non_contiguous_matches = get_analyses(db_session, q="ㅍㅇㅌ")

    assert [analysis.id for analysis in prefix_matches] == [pjmetal.id]
    assert [analysis.id for analysis in middle_matches] == [pjmetal.id]
    assert [analysis.id for analysis in suffix_matches] == [pjmetal.id]
    assert non_contiguous_matches == []


def test_get_analyses_page_returns_slice_and_total(db_session: Session) -> None:
    run = create_run(db_session, memo="page target")
    first = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="claude",
            markdown="first markdown",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    second = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="000660",
            name="SK Hynix",
            model="claude",
            markdown="second markdown",
            judgment="보유",
            trend="횡보",
            cloud_position="구름 속",
            ma_alignment="혼조",
        ),
    )
    third = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="035420",
            name="NAVER",
            model="claude",
            markdown="third markdown",
            judgment="매도",
            trend="하락",
            cloud_position="구름 아래",
            ma_alignment="역배열",
        ),
    )

    first_page = get_analyses_page(db_session, page=1, page_size=2)
    second_page = get_analyses_page(db_session, page=2, page_size=2)

    assert [analysis.id for analysis in first_page.items] == [third.id, second.id]
    assert [analysis.id for analysis in second_page.items] == [first.id]
    assert first_page.total == 3
    assert first_page.total_pages == 2


def test_calc_entry_gap_pct_uses_nearest_entry_range_boundary() -> None:
    assert calc_entry_gap_pct(current_price=105, entry_price=100, entry_price_max=110) == 0
    assert calc_entry_gap_pct(current_price=98, entry_price=100, entry_price_max=110) == pytest.approx(2.0408, rel=1e-4)
    assert calc_entry_gap_pct(current_price=112, entry_price=100, entry_price_max=110) == pytest.approx(1.7857, rel=1e-4)
    assert calc_entry_gap_pct(current_price=None, entry_price=100, entry_price_max=None) is None


def test_get_analyses_page_filters_and_sorts_by_entry_gap(db_session: Session) -> None:
    run = create_run(db_session, memo="entry gap target")
    inside_range = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="111111",
            name="Inside Range",
            model="claude",
            markdown="inside markdown",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
            entry_price=100,
            entry_price_max=110,
        ),
    )
    near_single = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="222222",
            name="Near Single",
            model="claude",
            markdown="near markdown",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
            entry_price=100,
        ),
    )
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="333333",
            name="Far Single",
            model="claude",
            markdown="far markdown",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
            entry_price=100,
        ),
    )
    upsert_stock_price(db_session, ticker="111111", price_date=date.today(), close_price=105)
    upsert_stock_price(db_session, ticker="222222", price_date=date.today(), close_price=102)
    upsert_stock_price(db_session, ticker="333333", price_date=date.today(), close_price=110)

    page = get_analyses_page(db_session, entry_gap_lte=2, page=1, page_size=25)

    assert [item.id for item in page.items] == [inside_range.id, near_single.id]
    assert page.total == 2
    assert page.items[0].entry_gap_pct == 0
    assert page.items[0].is_entry_near is True


def test_get_analyses_page_filters_each_entry_candidate_separately(db_session: Session) -> None:
    run = create_run(db_session, memo="entry candidate target")
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="444444",
            name="Between Candidates",
            model="claude",
            markdown="""
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 눌림 진입 | 지지선 부근 | 1,659원 |
| 돌파 진입 | 저항 돌파 | 1,998원 |
""",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
            entry_price=1659,
            entry_price_max=1998,
        ),
    )
    near_pullback = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="555555",
            name="Near Pullback",
            model="claude",
            markdown="""
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 눌림 진입 | 지지선 부근 | 1,659원 |
| 돌파 진입 | 저항 돌파 | 1,998원 |
""",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
            entry_price=1659,
            entry_price_max=1998,
        ),
    )
    near_breakout = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="666666",
            name="Near Breakout",
            model="claude",
            markdown="""
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 눌림 진입 | 지지선 부근 | 1,659원 |
| 돌파 진입 | 저항 돌파 | 1,998원 |
""",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
            entry_price=1659,
            entry_price_max=1998,
        ),
    )
    generic_entry = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="777777",
            name="Generic Entry",
            model="claude",
            markdown="""
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | 20주선 지지 확인 | 100원 |
""",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
            entry_price=100,
        ),
    )
    upsert_stock_price(db_session, ticker="444444", price_date=date.today(), close_price=1800)
    upsert_stock_price(db_session, ticker="555555", price_date=date.today(), close_price=1680)
    upsert_stock_price(db_session, ticker="666666", price_date=date.today(), close_price=1960)
    upsert_stock_price(db_session, ticker="777777", price_date=date.today(), close_price=101)

    page = get_analyses_page(db_session, entry_gap_lte=2, page=1, page_size=25)
    pullback_page = get_analyses_page(
        db_session,
        entry_gap_lte=2,
        entry_candidate="pullback",
        page=1,
        page_size=25,
    )
    breakout_page = get_analyses_page(
        db_session,
        entry_gap_lte=2,
        entry_candidate="breakout",
        page=1,
        page_size=25,
    )

    assert [item.id for item in page.items] == [generic_entry.id, near_pullback.id, near_breakout.id]
    assert [item.id for item in pullback_page.items] == [near_pullback.id]
    assert [item.id for item in breakout_page.items] == [near_breakout.id]
    assert [(candidate.label, candidate.gap_pct is not None) for candidate in page.items[0].entry_candidates] == [
        ("진입", True),
    ]


def test_get_analysis_history_orders_by_newest_first(db_session: Session) -> None:
    first_run = create_run(db_session, memo="history 1")
    second_run = create_run(db_session, memo="history 2")

    older = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gemini",
            markdown="older",
            judgment="보유",
            trend="횡보",
            cloud_position="구름 속",
            ma_alignment="혼조",
        ),
    )
    newer = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=second_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gemini",
            markdown="newer",
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
            model="gemini",
            markdown="other ticker",
            judgment="보유",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )

    history = get_analysis_history(db_session, "005930")

    assert [analysis.id for analysis in history] == [newer.id, older.id]
    assert get_analysis(db_session, newer.id).ticker == "005930"


def test_upsert_stock_price_uses_seoul_time(db_session: Session) -> None:
    stock_price = upsert_stock_price(
        db_session,
        ticker="005930",
        price_date=date(2026, 4, 21),
        close_price=70000,
    )

    now_in_seoul = seoul_now().replace(tzinfo=None)
    assert abs(now_in_seoul - stock_price.fetched_at.replace(tzinfo=None)) < timedelta(seconds=5)


def test_job_lifecycle_updates_status(db_session: Session) -> None:
    run = create_run(db_session, memo="job run")
    job = create_job(db_session, ticker="005930", run_id=run.id)

    assert job.status == "pending"
    assert get_job(db_session, job.id) is not None

    update_job_failed(db_session, job, "pick: error")
    failed_job = get_job(db_session, job.id)
    assert failed_job is not None
    assert failed_job.status == "failed"
    assert failed_job.error_message == "pick: error"

    update_job_done(db_session, failed_job, analysis_id=123)
    done_job = get_job(db_session, job.id)
    assert done_job is not None
    assert done_job.status == "done"
    assert done_job.analysis_id == 123
    assert done_job.error_message is None
