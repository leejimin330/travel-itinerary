"""한국관광공사 TourAPI(KorService2) 클라이언트와 정규화.

필드명은 TourAPI 4.0 문서 기준이며, 실제 응답으로 확인되기 전까지는 가정이다.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import httpx

BASE_URL = "https://apis.data.go.kr/B551011/KorService2"
BUSAN_AREA_CODE = 6

# contentTypeId → 서비스 내부 카테고리
CONTENT_TYPE_CATEGORY = {
    12: "attraction",  # 관광지
    14: "culture",  # 문화시설
    15: "festival",  # 축제공연행사
    28: "leisure",  # 레포츠
    38: "shopping",  # 쇼핑
    39: "food",  # 음식점
}
# MVP 수집 대상 (숙박 32, 여행코스 25는 제외)
MVP_CONTENT_TYPES = (12, 14, 28, 38, 39)

# detailIntro2에서 영업시간·휴무일 필드명은 타입마다 다르다: (시간 필드, 휴무 필드)
HOURS_FIELDS = {
    12: ("usetime", "restdate"),
    14: ("usetimeculture", "restdateculture"),
    28: ("usetimeleports", "restdateleports"),
    38: ("opentime", "restdateshopping"),
    39: ("opentimefood", "restdatefood"),
}


@dataclass(frozen=True)
class PoiRecord:
    source_poi_id: str
    content_type_id: int
    category: str
    name: str
    address: str | None
    lon: float | None
    lat: float | None
    phone: str | None
    image_url: str | None
    area_code: int | None
    sigungu_code: int | None


def _clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _num(v, cast):
    s = _clean(v)
    if s is None:
        return None
    try:
        return cast(s)
    except ValueError:
        return None


def normalize_list_item(item: dict) -> PoiRecord | None:
    """areaBasedList2 한 건 → PoiRecord. 좌표나 이름이 없으면 일정에 못 쓰므로 None."""
    content_type_id = _num(item.get("contenttypeid"), int)
    category = CONTENT_TYPE_CATEGORY.get(content_type_id)
    lon, lat = _num(item.get("mapx"), float), _num(item.get("mapy"), float)
    name = _clean(item.get("title"))
    cid = _clean(item.get("contentid"))
    if not (category and name and cid and lon and lat):
        return None
    address = " ".join(p for p in (_clean(item.get("addr1")), _clean(item.get("addr2"))) if p)
    return PoiRecord(
        source_poi_id=cid,
        content_type_id=content_type_id,
        category=category,
        name=name,
        address=address or None,
        lon=lon,
        lat=lat,
        phone=_clean(item.get("tel")),
        image_url=_clean(item.get("firstimage")),
        area_code=_num(item.get("areacode"), int),
        sigungu_code=_num(item.get("sigungucode"), int),
    )


def extract_hours_text(content_type_id: int, intro: dict) -> str | None:
    """detailIntro2에서 영업시간·휴무일 원문을 합쳐 LLM 파서 입력으로 쓴다."""
    fields = HOURS_FIELDS.get(content_type_id)
    if not fields:
        return None
    labels = ("영업시간", "휴무일")
    parts = [f"{label}: {v}" for label, f in zip(labels, fields) if (v := _clean(intro.get(f)))]
    return "\n".join(parts) or None


class TourApiError(RuntimeError):
    pass


class TourApiClient:
    def __init__(self, key: str, *, base_url: str = BASE_URL, client: httpx.Client | None = None):
        self._key = key
        self._base = base_url.rstrip("/")
        self._http = client or httpx.Client(timeout=30)

    def _get(self, op: str, **params) -> dict:
        r = self._http.get(
            f"{self._base}/{op}",
            params={
                "serviceKey": self._key,
                "MobileOS": "ETC",
                "MobileApp": "travel-itinerary",
                "_type": "json",
                **params,
            },
        )
        r.raise_for_status()
        try:
            body = r.json()["response"]
        except (ValueError, KeyError) as e:  # 키 오류 시 XML 오류문이 온다
            raise TourApiError(f"{op}: 예상 밖 응답: {r.text[:200]}") from e
        code = body["header"]["resultCode"]
        if code != "0000":
            raise TourApiError(f"{op}: {code} {body['header'].get('resultMsg')}")
        return body["body"]

    @staticmethod
    def _items(body: dict) -> list[dict]:
        items = body.get("items")
        if not items:  # 결과 없음은 items == "" 로 온다
            return []
        item = items["item"]
        return item if isinstance(item, list) else [item]

    def area_based_list(
        self, *, area_code: int, content_type_id: int, page_size: int = 100
    ) -> Iterator[dict]:
        page = 1
        while True:
            body = self._get(
                "areaBasedList2",
                areaCode=area_code,
                contentTypeId=content_type_id,
                numOfRows=page_size,
                pageNo=page,
            )
            yield from self._items(body)
            if page * page_size >= int(body.get("totalCount", 0)):
                return
            page += 1

    def detail_common(self, content_id: str) -> dict | None:
        items = self._items(self._get("detailCommon2", contentId=content_id))
        return items[0] if items else None

    def detail_intro(self, content_id: str, content_type_id: int) -> dict | None:
        items = self._items(
            self._get("detailIntro2", contentId=content_id, contentTypeId=content_type_id)
        )
        return items[0] if items else None
