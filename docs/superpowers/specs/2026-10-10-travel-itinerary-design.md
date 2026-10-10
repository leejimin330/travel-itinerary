# 여행 일정 자동 생성 서비스 — 설계 문서 (MVP: 부산)

- 작성일: 2026-10-10
- 원본 명세: `~/Downloads/travel-itinerary-site.md` (이하 "원본 명세")
- 이 문서는 원본 명세를 기준으로, 브레인스토밍에서 확정한 결정사항과 MVP 범위·하위 프로젝트 분해를 정리한다. 원본 명세와 충돌하는 부분은 이 문서가 우선한다.

---

## 1. 목적과 성공 기준

**목적**: 실제 사용자에게 공개하는 서비스. 사용자의 여행 조건을 받아 관광지 추천 + 최적 동선 + 시간대별 일정을 생성한다.

**MVP 성공 기준**
1. 비회원이 "부모님이랑 부산 2박 3일, 많이 안 걷게" 같은 입력으로 30초 이내에 검증을 통과한 일정을 받는다.
2. 생성된 일정의 모든 방문이 영업시간·휴무일 제약을 만족한다 (검증 레이어 위반 0건).
3. 자동차 / 도보 / 대중교통 세 가지 이동수단 모두 일정 생성이 된다.
4. 사용자가 장소를 삭제·추가·순서 변경·잠금하면 해당 일자만 재최적화된다.
5. 모든 추천·편집 행동이 `feedback_log`에 남는다 (비회원 포함).
6. 카카오 로그인 후 일정을 저장하고 "내 일정"에서 다시 볼 수 있다.
7. VPS + Vercel에 배포되어 외부에서 접속 가능하다.

---

## 2. 확정된 결정사항

| 항목 | 결정 | 근거 |
|---|---|---|
| 서비스 성격 | 실제 공개 서비스 | 사용자 결정 |
| MVP 지역 | **부산** (TourAPI areaCode 6). 다음 확장: **서울** | 관광 권역이 뚜렷해 클러스터링·동선 효과가 잘 드러남 |
| 이동수단 | **자동차 + 도보 + 대중교통** 모두 MVP 포함 | 사용자 결정 |
| 회원 | 비회원으로 생성·편집 가능, **저장 시에만 카카오 로그인** (카카오만) | 첫 사용 장벽 최소화 + 익명 로그도 수집 |
| 배포 | **VPS 1대 (8GB급) + Docker Compose** 로 백엔드 전체, 프론트는 **Vercel** | 비용 예측 가능, 운영 단순 |
| 하위 프로젝트 분해 | **데이터부터 순서대로 쌓기** (§5) | 품질이 데이터·이동시간 정확도에 좌우됨 |
| 배치 작업 | Celery 대신 **APScheduler** (백엔드 내 별도 worker 컨테이너) | 주 1회 수준 작업에 충분, 구성요소 감소 |
| 임베딩 모델 | `intfloat/multilingual-e5-base` (768차원, CPU 추론) | 스키마의 `VECTOR(768)`과 일치, 한/일/영 지원 |
| LLM | 파싱류(조건, 영업시간): `claude-haiku-5-5` / 일정 설명: `claude-sonnet-5-5` | 파싱은 저비용·고속, 설명은 품질 |

### 2.1 외부 API 선택

| 용도 | 선택 | 비고 |
|---|---|---|
| POI | 한국관광공사 TourAPI (data.go.kr, 국문 관광정보 서비스) | DB 적재 가능. 개발계정으로 시작 → 운영 전 활용사례 등록 후 트래픽 증가 신청 |
| 지도 표시 | 카카오맵 JS SDK | 프론트 노출용 JavaScript 키는 도메인 제한으로 보호 |
| 자동차·도보 이동시간 | **OSRM 자체 운영** (OSM 한국 추출본, car·foot 프로필) | 호출 비용 0, 캐싱 제약 없음. 실시간 교통 미반영 → 자동차 시간에 계수 1.2 보정 |
| 대중교통 이동시간 | ODsay | 호출 한도가 작으므로 §4.3의 호출 예산 관리 필수 |
| 공휴일 | 한국천문연구원 특일정보 API (data.go.kr) | 공휴일 휴무 처리용 |
| 로그인 | 카카오 로그인 (REST API, OAuth) | |

**구현 착수 전 확인 항목** (하위 프로젝트 1·2 착수 시 각 약관 원문 확인):
- TourAPI 개발/운영계정 일일 트래픽 한도
- ODsay 요금제별 일일 한도와 **결과 저장(캐싱) 허용 여부**
  - 캐싱 불허 시: DB 영구 캐시(`travel_time_cache`)는 OSRM 결과에만 쓰고, ODsay 결과는 약관이 허용하는 범위의 단기 Redis 캐시만 사용한다.
- 카카오 로그인·지도 SDK 무료 사용량

---

## 3. MVP 범위

### 포함
- 부산 POI 수집 (TourAPI: 관광지, 문화시설, 음식점, 쇼핑 등 MVP에 필요한 콘텐츠 타입)
- 영업시간 텍스트 → LLM 구조화 → `poi_hours`, 공휴일 휴무 반영
- 콘텐츠 기반 추천 (원본 명세 Phase 1: `score = α·similarity + β·popularity`)
- 체류시간: 카테고리별 기본값 테이블 (예측 모델은 v1)
- 일자별 지리 클러스터링
- 이동시간 3종 + 2단계 캐싱
- OR-Tools Orienteering Problem with Time Windows
- 검증 레이어 + 실패 시 대체·재최적화
- 조건 파서, 일정 설명 생성 (LLM)
- 조건 입력 화면, 결과 화면(타임라인 + 카카오맵), 편집(드래그·삭제·잠금·비슷한 장소로 교체), POI 상세 모달
- 부분 재계획
- 카카오 로그인, 일정 저장, 내 일정 목록, 공유 링크
- `feedback_log` (비회원 포함)
- 오류 신고 (원본 명세에서는 v1이지만 공개 서비스라 데이터 신뢰도 관리를 위해 MVP로 당김)

### 제외 (원본 명세 로드맵 유지)
- AI Hub 지도학습 추천, 체류시간 예측 모델 → v1
- 서울 확장 → v1 (부산 다음)
- 일본, Entity Resolution(다중 소스) → v2
- 로그 기반 재학습, 날씨, 숙소 기준 출발·도착, 교통패스 → v3
  - 단, 조건 JSON에 `lodging`(좌표, 선택) 필드는 MVP부터 둔다. 값이 있으면 출발·도착점으로 쓰고, 없으면 그날 첫 장소에서 시작한다.

---

## 4. 아키텍처

### 4.1 구성

```
[Vercel] Next.js (TS, Tailwind, 카카오맵 SDK)
     │ HTTPS
     ▼
[VPS — Docker Compose]
  ├─ api        FastAPI (조건 파싱, 일정 생성/편집, POI, 인증)
  ├─ worker     APScheduler (TourAPI 동기화, 영업시간 파싱, 임베딩, confidence 감쇠)
  ├─ postgres   PostgreSQL 16 + PostGIS + pgvector
  ├─ redis      이동시간·API 응답 캐시, ODsay 호출 예산 카운터, rate limit
  ├─ osrm-car   OSRM (한국 OSM, car)
  ├─ osrm-foot  OSRM (한국 OSM, foot)
  └─ caddy      리버스 프록시 + 자동 TLS
```

로컬 개발도 같은 Compose 구성을 사용한다.

### 4.2 백엔드 모듈 경계

각 모듈은 인터페이스만 보고 사용할 수 있어야 하며, 내부 교체가 소비자에 영향을 주지 않는다.

| 모듈 | 책임 | 의존 |
|---|---|---|
| `ingest` | TourAPI 수집 → `poi`, `poi_source` | DB |
| `hours` | 영업시간 텍스트 → 구조화(LLM) → `poi_hours` | LLM 클라이언트, DB |
| `embedding` | POI 설명·사용자 선호 임베딩 | e5 모델 |
| `conditions` | 자연어 → 조건 JSON (Pydantic 스키마) | LLM 클라이언트 |
| `recommend` | 후보 POI 점수·체류시간 산출 (`Recommender` 인터페이스, Phase 1 구현체) | DB, embedding |
| `cluster` | 후보를 일자별로 묶기 | — |
| `routing` | 이동시간 행렬 (`Router` 인터페이스 → `OsrmRouter`, `OdsayRouter`; 국가 확장 시 `JapanRouter`) | OSRM, ODsay, Redis, DB |
| `optimizer` | OR-Tools 래퍼. 입력: 노드·time window·service time·행렬·고정 노드 / 출력: 일자별 순서·시각 | OR-Tools |
| `validate` | 원본 명세 §6.5 검사 목록 | DB(휴무일) |
| `planner` | 위 모듈을 엮는 오케스트레이션 (생성, 부분 재계획, 대체 루프) | 위 전부 |
| `explain` | 일정 설명 생성 (LLM) | LLM 클라이언트 |
| `auth` | 카카오 OAuth, 세션, 익명 ID 병합 | DB |
| `feedback` | `feedback_log` 기록 | DB |

### 4.3 이동시간 계산과 ODsay 호출 예산

1. 모든 후보 쌍을 직선거리 × 수단별 계수로 근사한다.
2. 클러스터링과 1차 최적화는 근사 행렬로 한다.
3. 1차 결과에 쓰인 구간과 인접 후보 구간만 실제 값을 조회한다.
   - 자동차·도보: OSRM `table` API (자체 서버라 한도 없음)
   - 대중교통: ODsay. 단, 다음 조건을 둔다.
     - 도보 15분 이하 구간은 ODsay를 호출하지 않고 도보로 처리한다.
     - Redis에 일일 호출 카운터를 두고, 일일 한도의 80%를 넘으면 신규 조회를 중단한다. 이후 그 구간은 근사값으로 쓰고 UI에 "추정" 배지를 단다.
4. 실제 값으로 행렬을 갱신해 재최적화한다.
5. 캐시: Redis(핫) + `travel_time_cache`(영구). TTL은 원본 명세를 따르되(대중교통 30일, 자동차 7일), 약관 확인 결과(§2.1)를 우선한다. OSRM 결과는 OSM 데이터를 갱신할 때만 무효화한다.

### 4.4 데이터 모델 변경 (원본 명세 §5 대비)

- 추가 `app_user`: id UUID, kakao_id BIGINT UNIQUE, nickname, created_at
- 추가 `anon_session`: id UUID (브라우저 쿠키), user_id UUID NULL (로그인 시 연결), created_at
- `itinerary`: `user_id`는 NULL 허용, `anon_id` 추가, `share_token` 추가 (공유 링크용)
- `itinerary_item`: `locked BOOLEAN`, `travel_mode VARCHAR`, `travel_estimated BOOLEAN` 추가
- `feedback_log`: `user_id`는 NULL 허용, `anon_id` 추가
- 추가 `poi_report`: id, poi_id, anon_id, user_id NULL, type(closed/hours_wrong/other), message, status, created_at
- 추가 `holiday`: date, name (특일정보 API 동기화)
- 추가 `stay_default`: category → 기본 체류시간(분)
- 그 외 원본 명세 §5의 테이블(`poi`, `poi_source`, `poi_hours`, `poi_closures`, `travel_time_cache`)은 그대로 쓴다.
- 마이그레이션 도구: Alembic

### 4.5 에러 처리 원칙

- **LLM 실패** (스키마 검증 실패 포함): 1회 재시도 → 그래도 실패하면
  - 조건 파서: 폼 입력으로 폴백 (사용자가 직접 선택)
  - 영업시간 파싱: confidence를 낮추고 "영업시간 확인 필요" 표시
  - 일정 설명: 설명 없이 일정만 출력
- **외부 이동시간 API 실패·한도 초과**: 근사값 + "추정" 배지. 일정 생성 자체는 실패시키지 않는다.
- **최적화 해 없음**: 하루 POI 수를 줄이거나 제약을 완화하며 최대 3회 재시도 → 그래도 없으면 사용자에게 조건 완화를 제안한다.
- **검증 실패**: 위반 POI를 같은 클러스터의 차순위 후보로 대체해 재최적화, 최대 3회. 남은 위반은 경고와 함께 출력한다. 영업시간 위반은 예외로, 해당 POI를 제거하고 출력한다.
- **TourAPI 동기화 실패**: 기존 데이터를 유지하고 재시도 일정을 잡는다. 서비스는 영향을 받지 않는다.

### 4.6 보안·운영

- API 키는 모두 서버 환경변수로 관리한다. 프론트에는 카카오 JavaScript 키(도메인 제한)만 노출한다.
- 일정 생성 API에 rate limit을 건다 (IP·익명 ID 기준, Redis). LLM·ODsay 비용 폭주를 막기 위함이다.
- Postgres는 일 1회 백업 (`pg_dump` → 외부 스토리지).
- 출처 표기: TourAPI(한국관광공사), OSM(ODbL)을 화면 하단에 표기한다.

---

## 5. 하위 프로젝트 분해

각 하위 프로젝트는 **별도의 스펙 → 구현 계획 → 구현** 사이클을 거친다. 이 문서는 전체 틀이며, 하위 프로젝트 스펙에서 세부를 확정한다.

### SP1. 데이터 기반
- 모노레포 골격 (`backend/`, `frontend/`, `infra/`), Docker Compose (postgres, redis)
- Alembic 마이그레이션: §4.4 포함 전체 스키마
- TourAPI 부산 수집 (목록 + 상세 + 소개 정보) → `poi`, `poi_source`
- 영업시간 LLM 파싱 → `poi_hours` / `poi_closures`, 공휴일 동기화
- 임베딩 생성, 카테고리 기본 체류시간
- **완료 기준**: 부산 POI가 적재되어 있고, 영업시간 구조화율과 파싱 실패 목록이 리포트로 나온다.

### SP2. 이동시간
- OSRM car·foot 컨테이너 (한국 OSM 추출본 전처리 스크립트)
- `Router` 인터페이스, `OsrmRouter`, `OdsayRouter`, 직선거리 근사
- 2단계 캐시, ODsay 호출 예산 관리
- **완료 기준**: 부산 POI 50개 행렬을 세 수단 모두 계산할 수 있고, 두 번째 호출은 전부 캐시에서 응답한다.

### SP3. 일정 엔진 (API 전용)
- 조건 파서, Phase 1 추천, 클러스터링, OR-Tools OPTW, 검증 레이어, 대체 루프, 부분 재계획, 일정 설명
- `/api/conditions/parse`, `/api/itineraries` (POST/GET/PATCH), `/api/pois/*`
- `feedback_log` 기록 (recommended / removed / added / reordered)
- **완료 기준**: 시나리오 세트(§6)를 API로 실행하면 전부 검증을 통과한 일정이 나온다.

### SP4. 웹 앱
- Next.js: 조건 입력·확인 폼, 결과(일자 탭 + 타임라인 + 카카오맵 경로·번호 마커), 편집, POI 상세 모달, 오류 신고
- 익명 세션, 카카오 로그인, 저장, 내 일정, 공유 링크
- **완료 기준**: §1의 성공 기준 1·4·5·6을 브라우저에서 확인할 수 있다.

### SP5. 배포·운영
- VPS 프로비저닝, Compose 운영 구성 (caddy, worker 스케줄), Vercel 연결
- 백업, rate limit, 에러 로그 수집, 출처 표기
- **완료 기준**: 공개 URL에서 성공 기준 1~7 전부 확인.

순서: SP1 → SP2 → SP3 → SP4 → SP5. SP4의 화면 골격(정적 목업)은 SP3과 병행할 수 있다.

---

## 6. 테스트 전략

- **단위**: `optimizer`, `validate`, `cluster`, `hours` 파서 후처리는 순수 함수로 두고 TDD로 작성한다.
- **LLM 의존 모듈**: LLM 클라이언트를 주입해 고정 응답으로 테스트한다. 실제 호출 회귀 테스트는 소수의 골든 샘플로 별도 실행한다.
- **외부 API**: `Router` 구현체는 녹화된 응답으로 테스트하고, 실제 호출은 수동 스모크 테스트로만 한다.
- **시나리오 세트** (엔드투엔드, SP3부터):
  1. 부모님 동반, 부산 2박 3일, 자동차, 적게 걷기
  2. 친구, 부산 1일, 대중교통, 맛집·카페 위주
  3. 혼자, 부산 3일, 도보 + 대중교통, 바다·전통시장
  4. 월요일 출발 (월요일 휴무 POI 다수 포함)
  5. 공휴일 포함 일정
- **품질 지표**: 원본 명세 §10 중 "일정 품질"(이동시간 비율, 제약 위반 수, 검증 실패율)을 시나리오 세트 실행 시 자동 리포트로 출력한다.
