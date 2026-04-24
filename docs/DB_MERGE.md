# 로컬 DB 머지 가이드 (runs + analyses)

다른 머신의 `greed.db` 에 쌓인 **runs / analyses** 를 현재 머신의 `greed.db` 에 합치는 절차.

## 전제

- 두 머신 모두 같은 greed 스키마 (`backend/models.py`) 사용
- `runs.id` / `analyses.id` 는 autoincrement → 단순 dump/restore 불가
- 머지 스크립트 `scripts/merge_db.py` 가 **ID 재매핑** 방식으로 처리
- 대상 범위: `runs`, `analyses` **만**. `stock_prices`, `analysis_jobs` 는 건드리지 않음

## 용어

- **source** : 데이터를 가져올 머신 (예: 기존에 쓰던 노트북)
- **target** : 데이터를 합칠 머신 (작업을 실행할 머신)

---

## 1) source 측 — greed.db 추출

1. 백엔드 서버 / 분석 워커 중단 (SQLite WAL 잠금 방지)
   ```
   # uvicorn, claude 관련 프로세스 모두 종료
   ```
2. DB 무결성 확인
   ```
   sqlite3 greed.db "PRAGMA integrity_check;"
   # → ok 가 나와야 함
   ```
3. `c:\work\greed\greed.db` 파일을 target 머신으로 전송
   - USB / 네트워크 공유 / scp / 클라우드 드라이브 중 편한 방법
   - 파일 크기는 작음 (수백 KB 수준)

## 2) target 측 — 사전 준비

1. target 의 백엔드 서버 / 분석 워커 중단
2. 최신 머지 스크립트 pull
   ```
   cd c:/work/greed
   git pull
   ```
3. **기존 DB 백업** (필수)
   ```
   cp greed.db greed.db.backup.$(date +%Y%m%d_%H%M%S)
   ```
4. source 에서 받은 파일을 **`greed_source.db`** 이름으로 프로젝트 루트에 배치
   ```
   mv /path/to/받은/greed.db c:/work/greed/greed_source.db
   ```
   이 상태에서 `c:\work\greed\` 폴더:
   - `greed.db` — target 의 기존 DB (건드리지 않음)
   - `greed_source.db` — source 에서 가져온 DB
   - `greed.db.backup.YYYYMMDD_HHMMSS` — 롤백용 백업

## 3) 머지 실행

**Step 1. dry-run 으로 건수 확인** (rollback, 저장 안 됨)

```
cd c:/work/greed
.venv/Scripts/python.exe scripts/merge_db.py \
    --source greed_source.db \
    --target greed.db \
    --dry-run
```

출력 예시:
```
[DRY-RUN] rollback 완료. 실제 저장되지 않았습니다.
  - runs: 3 개 이전
    (새 run_id 범위: 4 ~ 6)
  - analyses: 7 개 이전
```

**Step 2. 본 실행**

```
.venv/Scripts/python.exe scripts/merge_db.py \
    --source greed_source.db \
    --target greed.db
```

출력 예시:
```
[COMMIT] 머지 완료.
  - runs: 3 개 이전
    (새 run_id 범위: 4 ~ 6)
  - analyses: 7 개 이전
```

## 4) 검증

1. 건수 확인
   ```
   sqlite3 greed.db "SELECT COUNT(*) FROM runs;"
   sqlite3 greed.db "SELECT COUNT(*) FROM analyses;"
   ```
   → (기존 target 건수 + source 건수) 와 일치해야 함
2. 백엔드 재기동 후 UI 에서:
   - Run 목록에 source 쪽 run 들이 **새 id** 로 보이는지
   - 분석 상세 클릭 → markdown 렌더링 정상
   - 티커 / 종목명 검색 정상 (`name_initials` 인덱스 복사됨)

## 5) 정리

- 이상 없으면 `greed_source.db` 삭제
- 백업 파일(`greed.db.backup.*`) 은 하루 이틀 유지 후 삭제

## 롤백

문제 발생 시:

```
# 백엔드 중단
cp greed.db.backup.YYYYMMDD_HHMMSS greed.db
# 백엔드 재기동
```

---

## 동작 원리

- source 의 각 `Run` 을 target 에 새 row 로 insert → autoincrement 로 새 `id` 획득
- `{old_run_id: new_run_id}` 맵 유지
- source 의 각 `Analysis` 는 `run_id` 만 새 id 로 치환하고 나머지 컬럼 그대로 복사
- `created_at` 은 원본 값 유지 (기본값 `seoul_now()` 으로 덮어쓰지 않음)
- 단일 트랜잭션 — 중간에 실패하면 전체 rollback
- `--dry-run` 은 commit 대신 rollback

## 주의

- 중복 감지 없음. 같은 스크립트를 두 번 돌리면 같은 데이터가 2벌 들어감
- 양방향 동기화 아님 (source → target 단방향, 일회성)
- 반복 동기화가 필요해지면 `source_run_uuid` 같은 식별자 컬럼을 추가해 별도 설계 필요
