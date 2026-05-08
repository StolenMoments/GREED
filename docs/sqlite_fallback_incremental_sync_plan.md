# SQLite Fallback 분석 데이터 증분 동기화 기획안

## 배경

MariaDB 연결 실패 시 애플리케이션은 로컬 `greed.db` SQLite로 fallback하여 분석 데이터를 계속 저장할 수 있다. 이후 MariaDB 연결이 복구되면 SQLite에만 존재하는 분석 결과를 MariaDB에 추가해야 한다.

현재 `scripts/import_sqlite_analyses_to_mariadb.py`는 SQLite의 모든 `analyses` 행을 MariaDB의 최대 `runs.id`에 그대로 추가한다. 중복 검사를 하지 않으므로 fallback 기간 동안 생성된 분석만 안전하게 추가하는 용도로는 부족하다.

## 목표

- SQLite `greed.db`에만 저장된 분석만 MariaDB에 추가한다.
- 이미 MariaDB에 존재하는 분석은 다시 추가하지 않는다.
- SQLite와 MariaDB의 auto-increment `id`가 달라도 동일 분석을 판별할 수 있어야 한다.
- fallback 중 생성되는 job 산출물이 MariaDB job 산출물과 충돌하지 않아야 한다.
- 실행 전 dry-run으로 추가/스킵 건수를 확인할 수 있어야 한다.
- v1에서는 `analyses`만 동기화한다. `analysis_jobs`, `stock_prices`, 종목 마스터 데이터는 제외한다.

## 권장 설계

### 1. Job 산출물 경로 namespace 선행 적용

증분 동기화 구현 전에 job 산출물 경로를 DB별 namespace로 분리한다.

현재 job 산출물은 `pick_output/jobs/{job_id}`에 저장된다. MariaDB와 fallback SQLite는 서로 다른 auto-increment 공간을 가지므로, MariaDB의 `analysis_jobs.id=5`와 SQLite의 `analysis_jobs.id=5`가 같은 디렉터리를 공유할 수 있다. 이 경우 fallback job이 이전 MariaDB job의 `analysis.md`, `exit_code.txt`, `model.pid`를 읽어 잘못 완료 처리될 수 있다.

권장 경로:

```text
pick_output/jobs/{db_namespace}/{job_id}/
```

`db_namespace` 규칙:

- SQLite: `sqlite-` + `sha256(greed.db 절대경로)[:12]`
- MariaDB/MySQL: `mariadb-` + `sha256(password 제거된 DATABASE_URL)[:12]`
- URL은 `make_url(...).render_as_string(hide_password=True)`로 비밀번호를 제거한 뒤 hash한다.

수정 대상:

- `backend.routers.jobs._job_output_dir(job_id)`
- 필요 시 `backend.database`에 현재 활성 DB namespace를 제공하는 helper 추가
- 기존 테스트의 예상 경로를 `jobs/{namespace}/{job_id}` 기준으로 갱신

추가 안전장치:

- 새 job 시작 시 해당 job 디렉터리의 `analysis.md`, `exit_code.txt`, `model.pid`를 제거한다.
- 가능하면 `job_meta.json`에 `job_id`, `ticker`, `model`, `db_namespace`, `created_at`을 저장하고 finalize 전에 현재 job과 일치하는지 검증한다.
- 과거 `pick_output/jobs/{job_id}` 구조의 디렉터리는 자동 마이그레이션하지 않는다. 새 구조 적용 후 생성되는 job만 namespace 경로를 사용한다.

### 2. 분석 식별자 `sync_key` 도입

`analyses`에 내용 기반 식별자를 추가한다.

```text
sync_key = sha256(
  ticker + "\n" +
  name + "\n" +
  model + "\n" +
  created_at.isoformat() + "\n" +
  markdown
)
```

- DB의 `id`는 SQLite와 MariaDB에서 달라질 수 있으므로 중복 판정 기준으로 사용하지 않는다.
- `markdown`을 포함해 같은 종목을 같은 모델로 여러 번 분석한 이력을 구분한다.
- `created_at`까지 포함해 같은 markdown을 재등록한 경우도 별도 이력으로 볼 수 있게 한다.
- 컬럼명은 `sync_key VARCHAR(64) NULL`로 추가하고, MariaDB에는 unique index를 둔다.

기존 데이터에는 마이그레이션 시 같은 규칙으로 `sync_key`를 역산해 채운다. 중복 데이터가 이미 존재하는 경우 unique index 생성 전에 중복 목록을 보고하고, 자동 삭제는 하지 않는다.

### 3. 동기화 CLI 추가

새 스크립트 예시:

```powershell
python scripts/sync_sqlite_analyses_to_mariadb.py `
  --source .\greed.db `
  --target "mysql+pymysql://USER:PASSWORD@HOST:3306/greed?charset=utf8mb4" `
  --dry-run
```

실제 반영:

```powershell
python scripts/sync_sqlite_analyses_to_mariadb.py `
  --source .\greed.db `
  --commit
```

동작 순서:

1. SQLite source schema 확인
2. MariaDB target schema 확인
3. source 분석별 `sync_key` 계산
4. target의 기존 `sync_key` 집합 조회
5. target에 없는 분석만 insert
6. dry-run이면 rollback, commit이면 commit
7. 결과 출력

출력 예시:

```text
[DRY-RUN] sqlite analysis sync completed
  - source_analyses: 120
  - existing_analyses: 95
  - insertable_analyses: 25
  - inserted_analyses: 0
  - target_run_id: 8
```

### 4. Run 매핑 정책

v1 기본 정책은 MariaDB에 동기화 전용 run을 하나 만들고, SQLite에만 있던 분석을 모두 해당 run에 연결한다.

```text
memo = "[SQLite Sync] 2026-05-08 fallback analyses"
```

옵션:

- `--target-run-id`: 기존 MariaDB run에 붙인다.
- `--create-run-memo`: 새 run의 memo를 직접 지정한다.

SQLite의 원래 `run_id`를 그대로 보존하는 방식은 v2로 미룬다. 이를 하려면 `runs`도 중복 판정과 매핑 규칙이 필요하다.

## 구현 위치

- `backend.routers.jobs`: job 산출물 경로를 DB namespace 포함 구조로 변경
- `backend.models.Analysis`: `sync_key` 컬럼과 unique index 추가
- `backend.database._migrate_sqlite`: SQLite 컬럼/인덱스 보정 추가
- 신규 스크립트: `scripts/sync_sqlite_analyses_to_mariadb.py`
- 기존 문서 `docs/분석데이터_추가마이그레이션.md`: 새 증분 동기화 스크립트 사용을 권장하도록 갱신

기존 `scripts/import_sqlite_analyses_to_mariadb.py`는 전체 추가용 legacy 도구로 유지하거나, 새 스크립트로 대체하고 문서에서 deprecated 처리한다.

## 테스트 계획

- MariaDB와 fallback SQLite에서 같은 `job_id`가 생겨도 서로 다른 산출물 디렉터리를 사용한다.
- fallback SQLite job은 같은 숫자의 이전 MariaDB job `analysis.md`를 읽어 완료 처리하지 않는다.
- 새 job 시작 시 같은 namespace/job 디렉터리에 남은 stale `analysis.md`, `exit_code.txt`, `model.pid`가 정리된다.
- 같은 분석이 MariaDB에 있으면 insert하지 않는다.
- markdown 또는 created_at이 다르면 같은 ticker/model이어도 별도 분석으로 insert한다.
- dry-run은 target DB를 변경하지 않는다.
- commit은 누락 분석만 insert한다.
- target에 run이 없으면 새 sync run을 생성한다.
- `--target-run-id`가 존재하지 않으면 실패한다.
- source SQLite에 필수 컬럼이 없으면 명확한 오류를 출력한다.
- MariaDB unique index 충돌이 발생하면 전체 transaction을 rollback한다.

## 이번 작업 범위 밖

- 자동 동기화 스케줄러
- 웹 관리자 화면
- `analysis_jobs` 동기화
- fallback 중 생성된 run 구조의 완전 보존
- 중복 데이터 자동 병합 또는 삭제
