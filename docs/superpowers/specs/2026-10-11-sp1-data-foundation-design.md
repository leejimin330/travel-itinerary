# SP1. 데이터 기반 — 스펙

상위 설계: `2026-10-10-travel-itinerary-design.md` §5 SP1. 완료 기준: 부산 POI가 적재되어 있고, 영업시간 구조화율과 파싱 실패 목록이 리포트로 나온다.

## 작업 순서

| # | 작업 | 상태 |
|---|---|---|
| 1 | 모노레포 골격, Docker Compose(postgres+postgis+pgvector, redis) | 작성됨, 기동 미확인(Docker 설치 후) |
| 2 | SQLAlchemy 모델 13개 테이블 | 작성됨 |
| 3 | Alembic 초기 마이그레이션 | **Docker 설치 후 `alembic revision --autogenerate`로 생성** |
| 4 | TourAPI 클라이언트·정규화 (`app/ingest/tourapi.py`) | 작성됨, 단위 테스트 통과 |
| 5 | 수집 파이프라인: 목록 → 상세 → `poi`/`poi_source` upsert | 미착수 |
| 6 | 영업시간 LLM 파싱 → `poi_hours`/`poi_closures` | 미착수 |
| 7 | 공휴일 동기화(`holiday`) | 미착수 |
| 8 | 임베딩(e5-base), `stay_default` 시드 | 미착수 |
| 9 | 구조화율·실패 목록 리포트 | 미착수 |

## 결정·가정

- 원본 명세 §5를 찾지 못해 `poi`, `poi_hours`, `poi_closures`, `travel_time_cache` 컬럼은 이 스펙에서 새로 정의했다. 원본이 있으면 대조한다.
- MVP 수집 contentTypeId: 12 관광지, 14 문화시설, 28 레포츠, 38 쇼핑, 39 음식점. 숙박(32)·축제(15)는 제외.
- 영업시간 원문은 detailIntro2의 타입별 필드(`usetime`, `opentimefood` 등)를 `poi.hours_text`에 합쳐 저장한다. 필드명은 실제 응답으로 확인 필요.
- 개발계정 일일 한도(자료상 1,000건)를 고려해 수집은 재개 가능해야 한다: `poi_source`에 이미 있는 건은 상세 호출을 건너뛴다.

## 착수 전 확인

- data.go.kr에서 "한국관광공사_국문 관광정보 서비스_GW" 활용신청 후 `TOURAPI_KEY` 설정
- 일일 트래픽 한도, 약관의 저장·캐싱 조건
