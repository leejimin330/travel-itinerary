import httpx
import respx

from app.ingest.tourapi import (
    BASE_URL,
    TourApiClient,
    TourApiError,
    extract_hours_text,
    normalize_list_item,
)

import pytest


def _ok(items, total=None):
    body = {"items": {"item": items} if items else "", "totalCount": total or len(items)}
    return httpx.Response(
        200, json={"response": {"header": {"resultCode": "0000", "resultMsg": "OK"}, "body": body}}
    )


ITEM = {
    "contentid": "126081", "contenttypeid": "12", "title": " 해운대해수욕장 ",
    "addr1": "부산광역시 해운대구 해운대해변로 264", "addr2": "(우동)",
    "mapx": "129.1603", "mapy": "35.1587", "tel": "", "firstimage": "http://x/a.jpg",
    "areacode": "6", "sigungucode": "16",
}


def test_normalize_list_item():
    r = normalize_list_item(ITEM)
    assert r.name == "해운대해수욕장"
    assert r.category == "attraction"
    assert (r.lon, r.lat) == (129.1603, 35.1587)
    assert r.address == "부산광역시 해운대구 해운대해변로 264 (우동)"
    assert r.phone is None


def test_normalize_drops_items_without_coordinates_or_unknown_type():
    assert normalize_list_item({**ITEM, "mapx": ""}) is None
    assert normalize_list_item({**ITEM, "contenttypeid": "32"}) is None  # 숙박은 MVP 제외


def test_extract_hours_text_uses_type_specific_fields():
    intro = {"opentimefood": "11:00~21:00", "restdatefood": "매주 월요일"}
    assert extract_hours_text(39, intro) == "영업시간: 11:00~21:00\n휴무일: 매주 월요일"
    assert extract_hours_text(39, {"usetime": "09:00"}) is None
    assert extract_hours_text(32, intro) is None


@respx.mock
def test_area_based_list_paginates():
    route = respx.get(f"{BASE_URL}/areaBasedList2").mock(
        side_effect=[_ok([ITEM, ITEM], total=3), _ok([ITEM], total=3)]
    )
    c = TourApiClient("k")
    assert len(list(c.area_based_list(area_code=6, content_type_id=12, page_size=2))) == 3
    assert route.call_count == 2
    assert route.calls[0].request.url.params["serviceKey"] == "k"


@respx.mock
def test_empty_result_and_api_error():
    respx.get(f"{BASE_URL}/detailCommon2").mock(return_value=_ok([]))
    assert TourApiClient("k").detail_common("1") is None

    respx.get(f"{BASE_URL}/detailIntro2").mock(
        return_value=httpx.Response(
            200,
            json={"response": {"header": {"resultCode": "0030", "resultMsg": "SERVICE KEY IS NOT REGISTERED"}}},
        )
    )
    with pytest.raises(TourApiError):
        TourApiClient("k").detail_intro("1", 12)
