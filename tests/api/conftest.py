import secrets

import pytest
import requests
from requests.adapters import HTTPAdapter

from petstore import PNG_1X1, PetstoreClient, assert_not_found, assert_pet, assert_status


@pytest.fixture
def api_client():
    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})
        session.mount("https://", HTTPAdapter(max_retries=0))
        yield PetstoreClient(session)


@pytest.fixture
def pet_data(api_client):
    pet_id = secrets.randbelow(2**53 - 1) + 1
    pet = {
        "id": pet_id,
        "name": f"qa-guru-{pet_id}",
        "photoUrls": [f"https://example.com/qa-guru/{pet_id}.png"],
        "status": "available",
        "category": {"id": pet_id, "name": f"category-{pet_id}"},
        "tags": [{"id": pet_id, "name": f"tag-{pet_id}"}],
    }
    # Never overwrite or delete a pre-existing record in this shared service.
    assert_not_found(api_client.request("GET", f"/pet/{pet_id}"))
    try:
        yield pet
    finally:
        # The fixture owns this ID before POST, so cleanup also runs if POST
        # times out after the server has already created the pet.
        errors = []
        for method, allowed_statuses in (("DELETE", {200, 404}), ("GET", {404})):
            try:
                response = api_client.request(method, f"/pet/{pet_id}")
                if response.status_code not in allowed_statuses:
                    errors.append(f"{method}: HTTP {response.status_code}: {response.text[:500]}")
            except requests.RequestException as error:
                errors.append(f"{method}: {error}")
        assert not errors, "Pet cleanup failed:\n" + "\n".join(errors)


@pytest.fixture
def created_pet(api_client, pet_data):
    response = api_client.request("POST", "/pet", json=pet_data)
    assert_status(response, 200)
    assert_pet(response.json(), pet_data)
    return pet_data


@pytest.fixture
def image_data():
    return PNG_1X1
