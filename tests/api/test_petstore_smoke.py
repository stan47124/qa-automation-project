from copy import deepcopy

import allure

from petstore import assert_not_found, assert_pet, assert_status


@allure.epic("QA.Guru graduation project")
@allure.feature("API: Swagger Petstore v3")
@allure.story("Create a pet")
@allure.title("Создание питомца")
def test_create_pet(api_client, pet_data):
    response = api_client.request("POST", "/pet", json=pet_data)
    assert_status(response, 200)
    assert_pet(response.json(), pet_data)
    saved = api_client.request("GET", f"/pet/{pet_data['id']}")
    assert_status(saved, 200)
    assert_pet(saved.json(), pet_data)


@allure.epic("QA.Guru graduation project")
@allure.feature("API: Swagger Petstore v3")
@allure.story("Read a pet")
@allure.title("Получение питомца по ID")
def test_get_pet_by_id(api_client, created_pet):
    response = api_client.request("GET", f"/pet/{created_pet['id']}")
    assert_status(response, 200)
    assert_pet(response.json(), created_pet)


@allure.epic("QA.Guru graduation project")
@allure.feature("API: Swagger Petstore v3")
@allure.story("Update a pet")
@allure.title("Обновление питомца")
def test_update_pet(api_client, created_pet):
    updated = deepcopy(created_pet)
    updated.update(
        name=f"updated-{created_pet['id']}",
        status="sold",
        photoUrls=[f"https://example.com/updated/{created_pet['id']}.png"],
        category={"id": created_pet["id"], "name": "updated-category"},
        tags=[{"id": created_pet["id"], "name": "updated-tag"}],
    )
    response = api_client.request("PUT", "/pet", json=updated)
    assert_status(response, 200)
    assert_pet(response.json(), updated)
    saved = api_client.request("GET", f"/pet/{created_pet['id']}")
    assert_status(saved, 200)
    assert_pet(saved.json(), updated)


@allure.epic("QA.Guru graduation project")
@allure.feature("API: Swagger Petstore v3")
@allure.story("Search by status")
@allure.title("Поиск питомцев по статусу")
def test_find_pets_by_status(api_client, created_pet):
    response = api_client.request(
        "GET", "/pet/findByStatus", params={"status": created_pet["status"]}
    )
    assert_status(response, 200)
    pets = response.json()
    assert isinstance(pets, list), pets
    assert all(isinstance(pet, dict) for pet in pets)
    assert all(pet.get("status") == created_pet["status"] for pet in pets)
    own_pets = [pet for pet in pets if pet.get("id") == created_pet["id"]]
    assert len(own_pets) == 1, f"Expected our pet exactly once; found {len(own_pets)}"
    assert_pet(own_pets[0], created_pet)


@allure.epic("QA.Guru graduation project")
@allure.feature("API: Swagger Petstore v3")
@allure.story("Upload a pet image")
@allure.title("Загрузка изображения: фактический ответ Pet")
def test_upload_pet_image(api_client, created_pet, image_data):
    response = api_client.request(
        "POST",
        f"/pet/{created_pet['id']}/uploadImage",
        params={"additionalMetadata": f"qa-guru-image-{created_pet['id']}"},
        data=image_data,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert_status(response, 200)
    uploaded = response.json()
    # PoC: the service returns Pet, not the documented ApiResponse.
    unchanged = {key: value for key, value in created_pet.items() if key != "photoUrls"}
    assert_pet(uploaded, unchanged)
    photos = uploaded["photoUrls"]
    assert len(photos) == len(created_pet["photoUrls"]) + 1
    assert photos[:-1] == created_pet["photoUrls"]
    assert photos[-1] and photos[-1] not in created_pet["photoUrls"]
    saved = api_client.request("GET", f"/pet/{created_pet['id']}")
    assert_status(saved, 200)
    assert_pet(saved.json(), {**created_pet, "photoUrls": photos})


@allure.epic("QA.Guru graduation project")
@allure.feature("API: Swagger Petstore v3")
@allure.story("Delete a pet")
@allure.title("Удаление питомца с последующим GET → 404")
def test_delete_pet(api_client, created_pet):
    response = api_client.request("DELETE", f"/pet/{created_pet['id']}")
    assert_status(response, 200)
    assert_not_found(api_client.request("GET", f"/pet/{created_pet['id']}"))


@allure.epic("QA.Guru graduation project")
@allure.feature("API: Swagger Petstore v3")
@allure.story("Reject an invalid ID")
@allure.title("Отклонение нечислового ID")
def test_reject_non_numeric_pet_id(api_client, created_pet):
    invalid_id = f"invalid-{created_pet['id']}"
    response = api_client.request("GET", f"/pet/{invalid_id}")
    assert_status(response, 400)
    error = response.json()
    assert isinstance(error, dict), error
    assert error.get("code") == 400
    assert isinstance(error.get("message"), str)
    assert invalid_id in error["message"]
    saved = api_client.request("GET", f"/pet/{created_pet['id']}")
    assert_status(saved, 200)
    assert_pet(saved.json(), created_pet)


@allure.epic("QA.Guru graduation project")
@allure.feature("API: Swagger Petstore v3")
@allure.story("Reject an invalid status")
@allure.title("Отклонение недопустимого статуса поиска")
def test_reject_invalid_status(api_client, created_pet):
    invalid_status = f"invalid-{created_pet['id']}"
    response = api_client.request(
        "GET", "/pet/findByStatus", params={"status": invalid_status}
    )
    assert_status(response, 400)
    error = response.json()
    assert isinstance(error, dict), error
    assert error.get("code") == 400
    assert isinstance(error.get("message"), str)
    assert invalid_status in error["message"] and "status" in error["message"]
    saved = api_client.request("GET", f"/pet/{created_pet['id']}")
    assert_status(saved, 200)
    assert_pet(saved.json(), created_pet)
