# 여행 일정 자동 생성 서비스 (MVP: 부산)

설계: `docs/superpowers/specs/2026-10-10-travel-itinerary-design.md`
SP1(데이터 기반): `docs/superpowers/specs/2026-10-11-sp1-data-foundation-design.md`

## 로컬 개발

```bash
cp .env.example .env              # TOURAPI_KEY 등 채우기
docker compose -f infra/docker-compose.yml up -d
cd backend
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/alembic upgrade head
.venv/Scripts/pytest
```
