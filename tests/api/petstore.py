import json
import re

import allure
import requests


BASE_URL = "https://petstore3.swagger.io/api/v3"
REQUEST_TIMEOUT = 15
PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00"
    b"\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND"
    b"\xaeB`\x82"
)


class PetstoreClient:
    def __init__(self, session: requests.Session):
        self.session = session
        self.owned_pet_ids = set()

    def _is_owned(self, pet):
        return (
            isinstance(pet, dict)
            and type(pet.get("id")) is int
            and pet["id"] in self.owned_pet_ids
        )

    def _safe_pet(self, pet):
        if not self._is_owned(pet):
            return {"body": "unowned or unknown pet omitted"}
        name = pet.get("name")
        status = pet.get("status")
        return {
            "id": pet["id"],
            "name": (
                name if isinstance(name, str)
                and re.fullmatch(r"(?:qa-guru-|updated-)\d+", name) else "[redacted]"
            ),
            "status": (
                status if isinstance(status, str)
                and status in {"available", "pending", "sold"} else "[invalid or absent]"
            ),
            "photo_count": (
                len(pet["photoUrls"]) if isinstance(pet.get("photoUrls"), list) else None
            ),
            "tag_count": len(pet["tags"]) if isinstance(pet.get("tags"), list) else None,
            # Category/tag labels, photo paths and unknown fields are not logged.
        }

    def _safe_response(self, response):
        try:
            body = response.json()
        except ValueError:
            return {
                "body": (
                    "Pet not found" if response.text.strip() == "Pet not found"
                    else "non-JSON body omitted"
                ),
                "size_bytes": len(response.content),
            }
        if isinstance(body, list):
            own = [pet for pet in body if self._is_owned(pet)]
            return {
                "total_items": len(body),
                "own_pets": [self._safe_pet(pet) for pet in own],
                "other_items_omitted": len(body) - len(own),
            }
        if isinstance(body, dict) and "id" in body:
            return self._safe_pet(body)
        if isinstance(body, dict) and "code" in body:
            return {
                "code": body["code"] if type(body["code"]) is int else "[redacted]",
                "message": "server error text omitted",
            }
        return {"body": "unknown JSON body omitted"}

    def request(self, method, path, **kwargs):
        # Requests' adapter is configured with max_retries=0 in the fixture.
        # Redirects are also disabled so an unexpected response stays visible.
        payload = kwargs.get("json")
        if method == "POST" and path == "/pet" and isinstance(payload, dict):
            if (
                type(payload.get("id")) is int
                and re.fullmatch(r"qa-guru-\d+", str(payload.get("name")))
            ):
                self.owned_pet_ids.add(payload["id"])
        if path in {"/pet", "/pet/findByStatus"}:
            route = path
        elif re.fullmatch(r"/pet/[^/]+/uploadImage", path):
            route = "/pet/{petId}/uploadImage"
        elif re.fullmatch(r"/pet/[^/]+", path):
            route = "/pet/{petId}"
        else:
            route = "[unknown route]"
        verb = method if method in {"GET", "POST", "PUT", "DELETE"} else "[unknown method]"
        params = kwargs.get("params") if isinstance(kwargs.get("params"), dict) else {}
        request_info = {
            "method": verb,
            "base_url": BASE_URL,
            "route": route,
            "timeout_seconds": REQUEST_TIMEOUT,
        }
        if "status" in params:
            status = params["status"]
            request_info["status"] = (
                status if isinstance(status, str)
                and status in {"available", "pending", "sold"} else "[invalid status]"
            )
        if payload is not None:
            request_info["json"] = self._safe_pet(payload)
        if "data" in kwargs:
            binary = kwargs["data"]
            request_info["binary_size_bytes"] = (
                len(binary) if isinstance(binary, bytes) else "[body omitted]"
            )
        # Headers, cookies, arbitrary params/URLs and binary contents are never attached.
        with allure.step(f"{verb} {route}"):
            allure.attach(
                json.dumps(request_info, ensure_ascii=False),
                "Request (allowlisted)", allure.attachment_type.JSON,
            )
            try:
                response = self.session.request(
                    method, f"{BASE_URL}{path}", timeout=REQUEST_TIMEOUT,
                    allow_redirects=False, **kwargs,
                )
            except requests.RequestException as error:
                allure.attach(type(error).__name__, "Transport error type", allure.attachment_type.TEXT)
                raise
            safe = {
                "http_status": response.status_code,
                "elapsed_seconds": response.elapsed.total_seconds(),
                "body": self._safe_response(response),
            }
            allure.attach(
                json.dumps(safe, ensure_ascii=False),
                "Response (allowlisted)", allure.attachment_type.JSON,
            )
            return response


def assert_status(response, expected):
    assert response.status_code == expected, (
        f"{response.request.method} {response.url}: expected {expected}, "
        f"got {response.status_code}; body={response.text[:1000]}"
    )


def assert_pet(actual, expected):
    """Validate required Pet fields and all values sent by this test."""
    assert isinstance(actual, dict), actual
    assert type(actual.get("id")) is int, actual
    assert isinstance(actual.get("name"), str) and actual["name"], actual
    assert isinstance(actual.get("photoUrls"), list), actual
    assert all(isinstance(url, str) and url for url in actual["photoUrls"]), actual
    assert actual.get("status") in {"available", "pending", "sold"}, actual
    for field, value in expected.items():
        assert field in actual, f"Missing {field}: {actual}"
        assert actual[field] == value, f"Field {field}: {actual[field]!r} != {value!r}"


def assert_not_found(response):
    assert_status(response, 404)
    # Observed response is plain text, even with an XML/JSON Content-Type.
    assert response.text.strip() == "Pet not found", response.text
