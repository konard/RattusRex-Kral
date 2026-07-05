import os
from datetime import date

os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from fastapi.testclient import TestClient

from app.db.database import Base, engine
from app.main import app


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_admin_seed_and_username_login():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["is_admin"] is True


def test_create_user_then_login_with_username_and_email():
    with TestClient(app) as client:
        created = client.post("/api/users", json={
            "username": "player-one",
            "email": "player-one@example.com",
            "password": "secret123"
        })
        assert created.status_code == 200, created.text
        assert created.json()["username"] == "player-one"

        username_token = login(client, "player-one", "secret123")
        username_response = client.get(
            "/api/me",
            headers={"Authorization": f"Bearer {username_token}"}
        )
        assert username_response.status_code == 200
        assert username_response.json()["email"] == "player-one@example.com"

        email_token = login(client, "player-one@example.com", "secret123")
        email_response = client.get(
            "/api/me",
            headers={"Authorization": f"Bearer {email_token}"}
        )
        assert email_response.status_code == 200
        assert email_response.json()["username"] == "player-one"


def test_duplicate_username_returns_conflict():
    with TestClient(app) as client:
        assert client.post("/api/users", json={
            "username": "player-two",
            "email": "player-two@example.com",
            "password": "secret123"
        }).status_code == 200

        duplicate = client.post("/api/users", json={
            "username": "player-two",
            "email": "different@example.com",
            "password": "secret123"
        })
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "Username already taken"


def test_duplicate_email_returns_conflict():
    with TestClient(app) as client:
        assert client.post("/api/users", json={
            "username": "player-three",
            "email": "player-three@example.com",
            "password": "secret123"
        }).status_code == 200

        duplicate = client.post("/api/users", json={
            "username": "differentuser",
            "email": "player-three@example.com",
            "password": "secret123"
        })
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "Email already registered"


def test_duplicate_email_case_insensitive_returns_conflict():
    with TestClient(app) as client:
        assert client.post("/api/users", json={
            "username": "player-four",
            "email": "player-four@example.com",
            "password": "secret123"
        }).status_code == 200

        duplicate = client.post("/api/users", json={
            "username": "player-four-v2",
            "email": "PLAYER-FOUR@EXAMPLE.COM",
            "password": "secret123"
        })
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "Email already registered"


def test_unique_user_registers_successfully():
    with TestClient(app) as client:
        response = client.post("/api/users", json={
            "username": "brandnewuser",
            "email": "brandnewuser@example.com",
            "password": "secret123"
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["username"] == "brandnewuser"
        assert data["email"] == "brandnewuser@example.com"


def test_password_hashing_uses_bcrypt_directly_without_passlib():
    """Registration must succeed with no passlib-related bcrypt version error.

    passlib 1.7.4 tried to read bcrypt.__about__.__version__, which was removed
    in bcrypt 4.1+, causing a trapped AttributeError and sometimes a cascading
    409 Conflict on valid registrations.  The fix replaces passlib with direct
    bcrypt calls so no version detection runs at all.
    """
    import logging
    import bcrypt as _bcrypt
    from app.core.security import hash_password, verify_password

    # Simulate an environment where bcrypt no longer exposes __about__
    original_about = getattr(_bcrypt, "__about__", None)
    try:
        if hasattr(_bcrypt, "__about__"):
            del _bcrypt.__about__

        hashed = hash_password("mypassword")
        assert hashed.startswith("$2b$"), "hash must be a valid bcrypt hash"
        assert verify_password("mypassword", hashed) is True
        assert verify_password("wrongpassword", hashed) is False
    finally:
        if original_about is not None:
            _bcrypt.__about__ = original_about

    # Confirm that registration itself returns 200 for a unique user
    with TestClient(app) as client:
        response = client.post("/api/users", json={
            "username": "bcrypt-compat-user",
            "email": "bcrypt-compat@example.com",
            "password": "secret123"
        })
        assert response.status_code == 200, response.text
        assert response.json()["username"] == "bcrypt-compat-user"


def test_admin_character_xp_rolls_over_remaining_xp():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Talia",
            "class_name": "Wizard",
            "level": 3,
            "route": "Arcane"
        })
        assert created.status_code == 200, created.text
        character_id = created.json()["id"]

        response = client.post(
            f"/api/admin/characters/{character_id}/xp",
            headers=headers,
            json={"amount": 6}
        )
        assert response.status_code == 200, response.text
        assert response.json()["level"] == 4
        assert response.json()["xp"] == 2


def test_player_character_patch_rejects_progression_and_death_state_changes():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        created_user = client.post("/api/users", json={
            "username": "patch-player",
            "email": "patch-player@example.com",
            "password": "secret123"
        })
        assert created_user.status_code == 200, created_user.text
        player_token = login(client, "patch-player", "secret123")
        player_headers = {"Authorization": f"Bearer {player_token}"}
        created_character = client.post("/api/characters", headers=player_headers, json={
            "name": "Grounded",
            "class_name": "Fighter",
            "level": 3,
            "route": "Steel",
            "hp": 0
        })
        assert created_character.status_code == 200, created_character.text
        character_id = created_character.json()["id"]

        seeded_state = client.patch(
            f"/api/admin/characters/{character_id}",
            headers=admin_headers,
            json={"level": 3, "xp": 1, "is_dead": True}
        )
        assert seeded_state.status_code == 200, seeded_state.text
        assert seeded_state.json()["is_dead"] is True

        forbidden = client.patch(
            f"/api/characters/{character_id}",
            headers=player_headers,
            json={"level": 20, "xp": 999, "is_dead": False}
        )
        assert forbidden.status_code == 422, forbidden.text

        unchanged = client.get(
            f"/api/admin/characters/{character_id}",
            headers=admin_headers
        )
        assert unchanged.status_code == 200, unchanged.text
        unchanged_payload = unchanged.json()
        assert unchanged_payload["level"] == 3
        assert unchanged_payload["xp"] == 1
        assert unchanged_payload["is_dead"] is True

        legitimate = client.patch(
            f"/api/characters/{character_id}",
            headers=player_headers,
            json={"name": "Renamed", "hp": 8}
        )
        assert legitimate.status_code == 200, legitimate.text
        legitimate_payload = legitimate.json()
        assert legitimate_payload["name"] == "Renamed"
        assert legitimate_payload["hp"] == 8
        assert legitimate_payload["level"] == 3
        assert legitimate_payload["xp"] == 1
        assert legitimate_payload["is_dead"] is True

        revived = client.post(
            f"/api/admin/characters/{character_id}/revive",
            headers=admin_headers
        )
        assert revived.status_code == 200, revived.text
        assert revived.json()["is_dead"] is False
        assert revived.json()["hp"] == 8


def test_players_cannot_directly_grant_inventory_currency_or_items():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        created_user = client.post("/api/users", json={
            "username": "mint-blocked",
            "email": "mint-blocked@example.com",
            "password": "secret123"
        })
        assert created_user.status_code == 200, created_user.text
        player_token = login(client, "mint-blocked", "secret123")
        player_headers = {"Authorization": f"Bearer {player_token}"}

        created_character = client.post("/api/characters", headers=player_headers, json={
            "name": "Honest Ledger",
            "class_name": "Bard",
            "level": 1,
            "route": "Market"
        })
        assert created_character.status_code == 200, created_character.text
        character_id = created_character.json()["id"]

        direct_currency = client.post(
            f"/api/characters/{character_id}/inventory/currency/add",
            headers=player_headers,
            json={"gold": 50, "silver": 5, "copper": 4}
        )
        assert direct_currency.status_code == 403
        direct_gold = client.post(
            f"/api/characters/{character_id}/inventory/gold/add",
            headers=player_headers,
            json={"amount": 50}
        )
        assert direct_gold.status_code == 403
        direct_item = client.post(
            f"/api/characters/{character_id}/inventory/items",
            headers=player_headers,
            json={"name": "Unreviewed Wand", "rarity": "Обычный", "is_consumable": False}
        )
        assert direct_item.status_code == 403

        inventory = client.get(
            f"/api/characters/{character_id}/inventory",
            headers=player_headers
        )
        assert inventory.status_code == 200, inventory.text
        assert inventory.json()["gold"] == 0
        assert inventory.json()["silver"] == 0
        assert inventory.json()["copper"] == 0
        assert inventory.json()["items"] == []

        granted_currency = client.post(
            f"/api/admin/characters/{character_id}/currency/add",
            headers=admin_headers,
            json={"gold": 5, "silver": 2, "copper": 1}
        )
        assert granted_currency.status_code == 200, granted_currency.text
        granted_item = client.post(
            f"/api/admin/characters/{character_id}/item",
            headers=admin_headers,
            json={"name": "Reviewed Wand", "rarity": "Обычный", "is_consumable": False}
        )
        assert granted_item.status_code == 200, granted_item.text
        assert granted_item.json()["gold"] == 5
        assert granted_item.json()["silver"] == 2
        assert granted_item.json()["copper"] == 1
        assert granted_item.json()["items"][0]["name"] == "Reviewed Wand"


def test_shop_search_charges_hireling_in_gold_before_buy_confirmation():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Borin",
            "class_name": "Fighter",
            "level": 1,
            "route": "Steel",
            "investigation": 20
        })
        character_id = created.json()["id"]
        client.post(
            f"/api/admin/characters/{character_id}/currency/add",
            headers=headers,
            json={"gold": 10000, "silver": 0, "copper": 0}
        )

        response = client.post(f"/api/characters/{character_id}/shop/search", headers=headers, json={
            "mode": "buy",
            "item_name": "Healing Potion",
            "rarity": "Обычный",
            "is_consumable": True,
            "searcher_type": "hireling",
            "hireling_level": "Эксперт"
        })
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["success"] is True
        assert payload["quote_id"]
        assert payload["item_price"] > 0
        assert payload["hireling_cost"] >= 25
        assert payload["inventory"]["gold"] == 10000 - payload["hireling_cost"]
        assert payload["inventory"]["items"] == []

        confirmed = client.post(
            f"/api/characters/{character_id}/shop/buy",
            headers=headers,
            json={"quote_id": payload["quote_id"]}
        )
        assert confirmed.status_code == 200, confirmed.text
        confirmed_payload = confirmed.json()
        assert confirmed_payload["is_consumed"] is True
        assert confirmed_payload["inventory"]["gold"] == (
            10000 - payload["hireling_cost"] - payload["item_price"]
        )
        assert confirmed_payload["inventory"]["items"][0]["name"] == "Healing Potion"


def test_shop_sell_search_waits_for_confirmation_and_adds_gold():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Mira",
            "class_name": "Rogue",
            "level": 1,
            "route": "Shadow",
            "investigation": 20
        })
        character_id = created.json()["id"]
        client.post(
            f"/api/admin/characters/{character_id}/currency/add",
            headers=headers,
            json={"gold": 1000, "silver": 0, "copper": 0}
        )
        granted = client.post(
            f"/api/admin/characters/{character_id}/item",
            headers=headers,
            json={"name": "Old Wand", "rarity": "Обычный", "is_consumable": False}
        )
        item_id = granted.json()["items"][0]["id"]

        response = client.post(f"/api/characters/{character_id}/shop/search", headers=headers, json={
            "mode": "sell",
            "item_id": item_id,
            "searcher_type": "hireling",
            "hireling_level": "Эксперт"
        })
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["success"] is True
        assert payload["inventory"]["items"][0]["name"] == "Old Wand"
        assert payload["inventory"]["gold"] == 1000 - payload["hireling_cost"]

        confirmed = client.post(
            f"/api/characters/{character_id}/shop/sell",
            headers=headers,
            json={"quote_id": payload["quote_id"]}
        )
        assert confirmed.status_code == 200, confirmed.text
        confirmed_payload = confirmed.json()
        assert confirmed_payload["inventory"]["items"] == []
        assert confirmed_payload["inventory"]["gold"] == (
            1000 - payload["hireling_cost"] + payload["item_price"]
        )


def test_magic_item_catalog_only_lists_allowed_rarities_and_supports_search():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/shop/magic-items", headers=headers)

        assert response.status_code == 200, response.text
        catalog = response.json()
        assert catalog
        assert {item["rarity"] for item in catalog} <= {"Обычный", "Необычный", "Редкий"}
        assert {item["rarity_key"] for item in catalog} <= {"common", "uncommon", "rare"}
        names = {item["name"] for item in catalog}
        assert "+1 Доспех" in names
        assert "+3 Доспех" not in names
        assert "Vorpal Sword" not in names
        assert all(item["item_type"] for item in catalog)

        search = client.get(
            "/api/shop/magic-items",
            headers=headers,
            params={"search": "щит", "rarity": "Необычный"}
        )

        assert search.status_code == 200, search.text
        search_payload = search.json()
        assert search_payload
        assert all("щит" in item["name"].casefold() for item in search_payload)
        assert all(item["rarity"] == "Необычный" for item in search_payload)


def test_shop_search_uses_selected_magic_item_without_manual_name_or_rarity():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Catalog Buyer",
            "class_name": "Fighter",
            "level": 1,
            "route": "Market",
            "investigation": 20
        })
        character_id = created.json()["id"]
        client.post(
            f"/api/admin/characters/{character_id}/currency/add",
            headers=headers,
            json={"gold": 10000, "silver": 0, "copper": 0}
        )
        catalog = client.get(
            "/api/shop/magic-items",
            headers=headers,
            params={"search": "+1 Доспех"}
        )
        magic_item = next(item for item in catalog.json() if item["name"] == "+1 Доспех")

        response = client.post(f"/api/characters/{character_id}/shop/search", headers=headers, json={
            "mode": "buy",
            "magic_item_id": magic_item["id"],
            "searcher_type": "character"
        })

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["success"] is True
        assert payload["item_name"] == "+1 Доспех"
        assert payload["rarity"] == "Редкий"
        assert payload["is_consumable"] is False
        assert payload["item_price"] > 0


def test_shop_buy_rejects_known_banned_magic_item_even_when_manual_rarity_lowered():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Ban Checker",
            "class_name": "Wizard",
            "level": 1,
            "route": "Market",
            "investigation": 20
        })
        character_id = created.json()["id"]

        response = client.post(f"/api/characters/{character_id}/shop/search", headers=headers, json={
            "mode": "buy",
            "item_name": "Vorpal Sword",
            "rarity": "Редкий",
            "is_consumable": False,
            "searcher_type": "character"
        })

        assert response.status_code == 400
        assert response.json()["detail"] == "Magic item is not available in the shop"


def test_admin_can_change_karma_and_view_all_characters_with_owner():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        created_user = client.post("/api/users", json={
            "username": "player-three",
            "email": "player-three@example.com",
            "password": "secret123"
        })
        assert created_user.status_code == 200, created_user.text
        user_id = created_user.json()["id"]
        player_token = login(client, "player-three", "secret123")
        player_headers = {"Authorization": f"Bearer {player_token}"}
        created_character = client.post("/api/characters", headers=player_headers, json={
            "name": "Nessa",
            "class_name": "Cleric",
            "level": 2,
            "route": "Dawn",
            "race": "Human",
            "subclass": "Life"
        })
        assert created_character.status_code == 200, created_character.text

        added = client.post(
            f"/api/admin/users/{user_id}/karma/add",
            headers=admin_headers,
            json={"amount": 3}
        )
        assert added.status_code == 200, added.text
        assert added.json()["karma"] == 3
        subtracted = client.post(
            f"/api/admin/users/{user_id}/karma/subtract",
            headers=admin_headers,
            json={"amount": 1}
        )
        assert subtracted.status_code == 200, subtracted.text
        assert subtracted.json()["karma"] == 2

        characters = client.get("/api/admin/characters", headers=admin_headers)
        assert characters.status_code == 200, characters.text
        payload = characters.json()
        assert any(
            character["name"] == "Nessa" and character["owner_username"] == "player-three"
            for character in payload
        )


def test_players_cannot_change_own_karma_through_me_endpoints():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        created_user = client.post("/api/users", json={
            "username": "karma-self-service",
            "email": "karma-self-service@example.com",
            "password": "secret123"
        })
        assert created_user.status_code == 200, created_user.text
        user_id = created_user.json()["id"]
        player_token = login(client, "karma-self-service", "secret123")
        player_headers = {"Authorization": f"Bearer {player_token}"}

        for path in ("/api/me/karma/add", "/api/me/karma/subtract"):
            blocked = client.post(path, headers=player_headers, json={"amount": 77})
            assert blocked.status_code == 404

        me = client.get("/api/me", headers=player_headers)
        assert me.status_code == 200, me.text
        assert me.json()["karma"] == 0

        added = client.post(
            f"/api/admin/users/{user_id}/karma/add",
            headers=admin_headers,
            json={"amount": 3}
        )
        assert added.status_code == 200, added.text
        assert added.json()["karma"] == 3


def test_admin_signed_adjustments_clamp_resources_to_zero():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        created_character = client.post("/api/characters", headers=headers, json={
            "name": "Vera",
            "class_name": "Wizard",
            "level": 20,
            "route": "Arcane"
        })
        assert created_character.status_code == 200, created_character.text
        character_id = created_character.json()["id"]

        added_xp = client.post(
            f"/api/admin/characters/{character_id}/xp",
            headers=headers,
            json={"amount": 10}
        )
        assert added_xp.status_code == 200, added_xp.text
        reduced_xp = client.post(
            f"/api/admin/characters/{character_id}/xp",
            headers=headers,
            json={"amount": -5}
        )
        assert reduced_xp.status_code == 200, reduced_xp.text
        assert reduced_xp.json()["xp"] == 5
        clamped_xp = client.post(
            f"/api/admin/characters/{character_id}/xp",
            headers=headers,
            json={"amount": -99}
        )
        assert clamped_xp.status_code == 200, clamped_xp.text
        assert clamped_xp.json()["xp"] == 0

        added_gold = client.post(
            f"/api/admin/characters/{character_id}/gold",
            headers=headers,
            json={"amount": 100}
        )
        assert added_gold.status_code == 200, added_gold.text
        reduced_gold = client.post(
            f"/api/admin/characters/{character_id}/gold",
            headers=headers,
            json={"amount": -25}
        )
        assert reduced_gold.status_code == 200, reduced_gold.text
        assert reduced_gold.json()["gold"] == 75
        clamped_gold = client.post(
            f"/api/admin/characters/{character_id}/gold",
            headers=headers,
            json={"amount": -999}
        )
        assert clamped_gold.status_code == 200, clamped_gold.text
        assert clamped_gold.json()["gold"] == 0

        created_user = client.post("/api/users", json={
            "username": "karma-target",
            "email": "karma-target@example.com",
            "password": "secret123"
        })
        assert created_user.status_code == 200, created_user.text
        user_id = created_user.json()["id"]
        added_karma = client.post(
            f"/api/admin/users/{user_id}/karma",
            headers=headers,
            json={"amount": 20}
        )
        assert added_karma.status_code == 200, added_karma.text
        reduced_karma = client.post(
            f"/api/admin/users/{user_id}/karma",
            headers=headers,
            json={"amount": -7}
        )
        assert reduced_karma.status_code == 200, reduced_karma.text
        assert reduced_karma.json()["karma"] == 13
        clamped_karma = client.post(
            f"/api/admin/users/{user_id}/karma",
            headers=headers,
            json={"amount": -99}
        )
        assert clamped_karma.status_code == 200, clamped_karma.text
        assert clamped_karma.json()["karma"] == 0


def test_admin_can_edit_any_character_directly():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        created_user = client.post("/api/users", json={
            "username": "editable-player",
            "email": "editable-player@example.com",
            "password": "secret123"
        })
        assert created_user.status_code == 200, created_user.text
        player_token = login(client, "editable-player", "secret123")
        player_headers = {"Authorization": f"Bearer {player_token}"}
        created_character = client.post("/api/characters", headers=player_headers, json={
            "name": "Old Name",
            "class_name": "Rogue",
            "level": 3,
            "route": "Old Path"
        })
        assert created_character.status_code == 200, created_character.text
        character_id = created_character.json()["id"]

        edited = client.patch(
            f"/api/admin/characters/{character_id}",
            headers=admin_headers,
            json={
                "name": "New Name",
                "class_name": "Воин",
                "subclass": "Champion",
                "race": "Human",
                "background": "Soldier",
                "route": "Iron",
                "level": 7,
                "xp": 4,
                "hp": 55,
                "armor_class": 18,
                "strength": 16,
                "dexterity": 12,
                "constitution": 14,
                "intelligence": 10,
                "wisdom": 11,
                "charisma": 9,
                "investigation": 6
            }
        )
        assert edited.status_code == 200, edited.text
        payload = edited.json()
        assert payload["name"] == "New Name"
        assert payload["level"] == 7
        assert payload["xp"] == 4
        assert payload["hp"] == 55
        assert payload["armor_class"] == 18
        assert payload["strength"] == 16
        assert payload["investigation"] == 6

        listed = client.get("/api/admin/characters", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        assert any(
            character["id"] == character_id and character["level"] == 7
            for character in listed.json()
        )


def test_user_cannot_create_more_than_ten_characters():
    with TestClient(app) as client:
        created_user = client.post("/api/users", json={
            "username": "collector",
            "email": "collector@example.com",
            "password": "secret123"
        })
        assert created_user.status_code == 200, created_user.text
        token = login(client, "collector", "secret123")
        headers = {"Authorization": f"Bearer {token}"}

        for index in range(10):
            response = client.post("/api/characters", headers=headers, json={
                "name": f"Hero {index}",
                "class_name": "Bard",
                "level": 1,
                "route": "Open Table"
            })
            assert response.status_code == 200, response.text

        blocked = client.post("/api/characters", headers=headers, json={
            "name": "Hero 11",
            "class_name": "Bard",
            "level": 1,
            "route": "Open Table"
        })
        assert blocked.status_code == 400
        assert blocked.json()["detail"] == "Достигнут лимит персонажей (10 из 10)."


def test_shop_buy_and_sell_confirmations_create_filterable_persistent_logs():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/api/me", headers=headers)
        assert me.status_code == 200, me.text
        user_id = me.json()["id"]
        created = client.post("/api/characters", headers=headers, json={
            "name": "Ledger",
            "class_name": "Fighter",
            "level": 1,
            "route": "Trade",
            "investigation": 20
        })
        assert created.status_code == 200, created.text
        character_id = created.json()["id"]
        currency = client.post(
            f"/api/admin/characters/{character_id}/currency/add",
            headers=headers,
            json={"gold": 10000, "silver": 0, "copper": 0}
        )
        assert currency.status_code == 200, currency.text

        buy_search = client.post(f"/api/characters/{character_id}/shop/search", headers=headers, json={
            "mode": "buy",
            "item_name": "Audit Sword",
            "rarity": "Обычный",
            "is_consumable": False,
            "searcher_type": "hireling",
            "hireling_level": "Эксперт"
        })
        assert buy_search.status_code == 200, buy_search.text
        buy_payload = buy_search.json()
        buy_confirm = client.post(
            f"/api/characters/{character_id}/shop/buy",
            headers=headers,
            json={"quote_id": buy_payload["quote_id"]}
        )
        assert buy_confirm.status_code == 200, buy_confirm.text

        granted = client.post(
            f"/api/admin/characters/{character_id}/item",
            headers=headers,
            json={"name": "Audit Wand", "rarity": "Обычный", "is_consumable": False}
        )
        assert granted.status_code == 200, granted.text
        sell_item_id = next(
            item["id"] for item in granted.json()["items"]
            if item["name"] == "Audit Wand"
        )
        sell_search = client.post(f"/api/characters/{character_id}/shop/search", headers=headers, json={
            "mode": "sell",
            "item_id": sell_item_id,
            "searcher_type": "hireling",
            "hireling_level": "Эксперт"
        })
        assert sell_search.status_code == 200, sell_search.text
        sell_payload = sell_search.json()
        sell_confirm = client.post(
            f"/api/characters/{character_id}/shop/sell",
            headers=headers,
            json={"quote_id": sell_payload["quote_id"]}
        )
        assert sell_confirm.status_code == 200, sell_confirm.text

    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        logs = client.get("/api/admin/shop-logs", headers=headers)
        assert logs.status_code == 200, logs.text
        payload = logs.json()
        assert len(payload) == 2
        buy_log = next(log for log in payload if log["mode"] == "buy")
        assert buy_log["username"] == "admin"
        assert buy_log["character_name"] == "Ledger"
        assert buy_log["item_name"] == "Audit Sword"
        assert buy_log["rarity"] == "Обычный"
        assert buy_log["item_price"] == buy_payload["item_price"]
        assert buy_log["hireling_cost"] == buy_payload["hireling_cost"]
        assert buy_log["total_amount"] == buy_payload["item_price"] + buy_payload["hireling_cost"]

        filtered = client.get(
            "/api/admin/shop-logs",
            headers=headers,
            params={
                "character_id": character_id,
                "user_id": user_id,
                "mode": "sell",
                "date": date.today().isoformat()
            }
        )
        assert filtered.status_code == 200, filtered.text
        sell_logs = filtered.json()
        assert len(sell_logs) == 1
        assert sell_logs[0]["item_name"] == "Audit Wand"
        assert sell_logs[0]["total_amount"] == sell_payload["item_price"] - sell_payload["hireling_cost"]


def test_admin_delete_character_requires_confirmation_and_cascades_inventory():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Delete Me",
            "class_name": "Fighter",
            "level": 1,
            "route": "Dust"
        })
        assert created.status_code == 200, created.text
        character_id = created.json()["id"]
        client.post(
            f"/api/admin/characters/{character_id}/currency/add",
            headers=headers,
            json={"gold": 5, "silver": 4, "copper": 3}
        )
        client.post(
            f"/api/admin/characters/{character_id}/item",
            headers=headers,
            json={"name": "Marked Sword", "rarity": "Обычный", "is_consumable": False}
        )

        blocked = client.delete(
            f"/api/admin/characters/{character_id}",
            headers=headers,
            params={"confirmation": "delete"}
        )
        assert blocked.status_code == 400

        removed = client.delete(
            f"/api/admin/characters/{character_id}",
            headers=headers,
            params={"confirmation": "УДАЛИТЬ"}
        )
        assert removed.status_code == 200, removed.text
        assert removed.json() == {"deleted": True, "id": character_id}

        listed = client.get("/api/admin/characters", headers=headers)
        assert listed.status_code == 200, listed.text
        assert all(character["id"] != character_id for character in listed.json())
        missing_inventory = client.get(
            f"/api/admin/characters/{character_id}/inventory",
            headers=headers
        )
        assert missing_inventory.status_code == 404


def test_cross_player_currency_and_item_transfers_create_persistent_logs():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        created_user = client.post("/api/users", json={
            "username": "receiver",
            "email": "receiver@example.com",
            "password": "secret123"
        })
        assert created_user.status_code == 200, created_user.text
        receiver_token = login(client, "receiver", "secret123")
        receiver_headers = {"Authorization": f"Bearer {receiver_token}"}

        sender = client.post("/api/characters", headers=admin_headers, json={
            "name": "Sender",
            "class_name": "Bard",
            "level": 1,
            "route": "Trade"
        })
        assert sender.status_code == 200, sender.text
        sender_id = sender.json()["id"]
        recipient = client.post("/api/characters", headers=receiver_headers, json={
            "name": "Recipient",
            "class_name": "Cleric",
            "level": 1,
            "route": "Trade"
        })
        assert recipient.status_code == 200, recipient.text
        recipient_id = recipient.json()["id"]

        targets = client.get("/api/characters/transfer-targets", headers=admin_headers)
        assert targets.status_code == 200, targets.text
        assert any(
            character["id"] == recipient_id and character["owner_username"] == "receiver"
            for character in targets.json()
        )

        currency = client.post(
            f"/api/admin/characters/{sender_id}/currency/add",
            headers=admin_headers,
            json={"gold": 2, "silver": 5, "copper": 4}
        )
        assert currency.status_code == 200, currency.text
        granted = client.post(
            f"/api/admin/characters/{sender_id}/item",
            headers=admin_headers,
            json={"name": "Courier Ring", "rarity": "Обычный", "is_consumable": False}
        )
        assert granted.status_code == 200, granted.text
        item_id = granted.json()["items"][0]["id"]

        insufficient = client.post(
            f"/api/characters/{sender_id}/inventory/currency/transfer",
            headers=admin_headers,
            json={"recipient_character_id": recipient_id, "gold": 9, "silver": 0, "copper": 0}
        )
        assert insufficient.status_code == 400

        transferred_currency = client.post(
            f"/api/characters/{sender_id}/inventory/currency/transfer",
            headers=admin_headers,
            json={"recipient_character_id": recipient_id, "gold": 1, "silver": 3, "copper": 4}
        )
        assert transferred_currency.status_code == 200, transferred_currency.text
        assert transferred_currency.json()["gold"] == 1
        assert transferred_currency.json()["silver"] == 2
        assert transferred_currency.json()["copper"] == 0

        invalid_item = client.post(
            f"/api/characters/{sender_id}/inventory/items/transfer",
            headers=admin_headers,
            json={"recipient_character_id": recipient_id, "item_id": item_id + 999}
        )
        assert invalid_item.status_code == 400

        transferred_item = client.post(
            f"/api/characters/{sender_id}/inventory/items/transfer",
            headers=admin_headers,
            json={"recipient_character_id": recipient_id, "item_id": item_id}
        )
        assert transferred_item.status_code == 200, transferred_item.text
        assert transferred_item.json()["items"] == []

        receiver_inventory = client.get(
            f"/api/characters/{recipient_id}/inventory",
            headers=receiver_headers
        )
        assert receiver_inventory.status_code == 200, receiver_inventory.text
        receiver_payload = receiver_inventory.json()
        assert receiver_payload["gold"] == 1
        assert receiver_payload["silver"] == 3
        assert receiver_payload["copper"] == 4
        assert receiver_payload["items"][0]["name"] == "Courier Ring"

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        logs = client.get("/api/admin/transfer-logs", headers=admin_headers)
        assert logs.status_code == 200, logs.text
        payload = logs.json()
        assert len(payload) == 2
        currency_log = next(log for log in payload if log["transfer_type"] == "currency")
        assert currency_log["sender_character_name"] == "Sender"
        assert currency_log["recipient_character_name"] == "Recipient"
        assert currency_log["gold"] == 1
        assert currency_log["silver"] == 3
        assert currency_log["copper"] == 4
        item_log = next(log for log in payload if log["transfer_type"] == "item")
        assert item_log["item_name"] == "Courier Ring"
        assert item_log["item_rarity"] == "Обычный"


def test_inventory_notes_combat_fields_and_attacks_persist_with_roll_log():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Sheet Hero",
            "class_name": "Воин",
            "level": 5,
            "route": "Frontline",
            "temp_hp": 8,
            "speed": 35,
            "strength": 16
        })
        assert created.status_code == 200, created.text
        character_id = created.json()["id"]
        assert created.json()["temp_hp"] == 8
        assert created.json()["speed"] == 35

        patched = client.patch(
            f"/api/characters/{character_id}",
            headers=headers,
            json={"temp_hp": 3, "speed": 40}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["temp_hp"] == 3
        assert patched.json()["speed"] == 40

        inventory = client.get(
            f"/api/characters/{character_id}/inventory",
            headers=headers
        )
        assert inventory.status_code == 200, inventory.text
        assert inventory.json()["notes"] == ""

        notes = "2 верёвки\n14 стрел\n3 факела"
        updated_notes = client.patch(
            f"/api/characters/{character_id}/inventory/notes",
            headers=headers,
            json={"notes": notes}
        )
        assert updated_notes.status_code == 200, updated_notes.text
        assert updated_notes.json()["notes"] == notes

        loaded_notes = client.get(
            f"/api/characters/{character_id}/inventory",
            headers=headers
        )
        assert loaded_notes.json()["notes"] == notes

        created_attack = client.post(
            f"/api/characters/{character_id}/attacks",
            headers=headers,
            json={
                "name": "Длинный меч",
                "attack_bonus": 5,
                "damage": "1d8+3 рубящий"
            }
        )
        assert created_attack.status_code == 200, created_attack.text
        attack_id = created_attack.json()["id"]

        attacks = client.get(
            f"/api/characters/{character_id}/attacks",
            headers=headers
        )
        assert attacks.status_code == 200, attacks.text
        assert attacks.json()[0]["name"] == "Длинный меч"
        assert attacks.json()[0]["damage"] == "1d8+3 рубящий"

        rolled = client.post(
            f"/api/characters/{character_id}/attacks/{attack_id}/roll",
            headers=headers
        )
        assert rolled.status_code == 200, rolled.text
        roll_payload = rolled.json()
        assert 1 <= roll_payload["roll"] <= 20
        assert roll_payload["bonus"] == 5
        assert roll_payload["total"] == roll_payload["roll"] + 5

        roll_messages = client.get(
            "/api/chat/messages",
            headers=headers,
            params={"channel": "rolls"}
        )
        assert roll_messages.status_code == 200, roll_messages.text
        assert any(
            message["formula"] == "1d20+5"
            and message["total"] == roll_payload["total"]
            and "Длинный меч" in message["content"]
            for message in roll_messages.json()
        )


def test_leaderboard_orders_users_by_karma_with_rank():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        users = []
        for username, karma in [
            ("leader-low", 3),
            ("leader-high", 11),
            ("leader-middle", 7)
        ]:
            created = client.post("/api/users", json={
                "username": username,
                "email": f"{username}@example.com",
                "password": "secret123"
            })
            assert created.status_code == 200, created.text
            users.append((created.json()["id"], username, karma))
            adjusted = client.post(
                f"/api/admin/users/{created.json()['id']}/karma",
                headers=admin_headers,
                json={"amount": karma}
            )
            assert adjusted.status_code == 200, adjusted.text

        leaderboard = client.get("/api/leaderboard", headers=admin_headers)
        assert leaderboard.status_code == 200, leaderboard.text
        payload = leaderboard.json()
        ranked = [
            (entry["rank"], entry["username"], entry["karma"])
            for entry in payload
            if entry["username"].startswith("leader-")
        ]
        assert ranked == [
            (1, "leader-high", 11),
            (2, "leader-middle", 7),
            (3, "leader-low", 3)
        ]


def test_chat_messages_and_dice_roll_commands_persist_to_channels():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}

        message = client.post(
            "/api/chat/messages",
            headers=headers,
            json={"content": "Кто идёт в экспедицию?"}
        )
        assert message.status_code == 200, message.text
        assert message.json()["channel"] == "general"
        assert message.json()["content"] == "Кто идёт в экспедицию?"

        general = client.get(
            "/api/chat/messages",
            headers=headers,
            params={"channel": "general"}
        )
        assert general.status_code == 200, general.text
        assert general.json()[0]["content"] == "Кто идёт в экспедицию?"

        roll = client.post(
            "/api/dice/roll",
            headers=headers,
            json={"formula": "/r 2d6"}
        )
        assert roll.status_code == 200, roll.text
        roll_payload = roll.json()
        assert roll_payload["formula"] == "2d6"
        assert len(roll_payload["rolls"]) == 2
        assert all(1 <= value <= 6 for value in roll_payload["rolls"])
        assert roll_payload["total"] == sum(roll_payload["rolls"])

        arbitrary = client.post(
            "/api/chat/messages",
            headers=headers,
            json={"content": "/r 1d37"}
        )
        assert arbitrary.status_code == 200, arbitrary.text
        assert arbitrary.json()["channel"] == "rolls"
        assert arbitrary.json()["formula"] == "1d37"
        assert len(arbitrary.json()["rolls"]) == 1
        assert 1 <= arbitrary.json()["rolls"][0] <= 37

        rolls = client.get(
            "/api/chat/messages",
            headers=headers,
            params={"channel": "rolls"}
        )
        assert rolls.status_code == 200, rolls.text
        formulas = [message["formula"] for message in rolls.json()]
        assert "2d6" in formulas
        assert "1d37" in formulas


def test_damage_roll_returns_dice_results_and_logs_to_rolls_channel():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Damage Roller",
            "class_name": "Воин",
            "level": 5,
            "route": "Frontline"
        })
        assert created.status_code == 200, created.text
        character_id = created.json()["id"]

        attack = client.post(
            f"/api/characters/{character_id}/attacks",
            headers=headers,
            json={"name": "Длинный меч", "attack_bonus": 5, "damage": "1d8+3"}
        )
        assert attack.status_code == 200, attack.text
        attack_id = attack.json()["id"]

        rolled = client.post(
            f"/api/characters/{character_id}/attacks/{attack_id}/roll-damage",
            headers=headers
        )
        assert rolled.status_code == 200, rolled.text
        payload = rolled.json()
        assert payload["attack_id"] == attack_id
        assert payload["name"] == "Длинный меч"
        assert len(payload["rolls"]) == 1
        assert 1 <= payload["rolls"][0] <= 8
        assert payload["modifier"] == 3
        assert payload["total"] == payload["rolls"][0] + 3

        roll_messages = client.get(
            "/api/chat/messages",
            headers=headers,
            params={"channel": "rolls"}
        )
        assert roll_messages.status_code == 200, roll_messages.text
        assert any(
            "Длинный меч" in message["content"] and "урон" in message["content"]
            for message in roll_messages.json()
        )


def test_damage_roll_fails_for_attack_without_damage():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "No Damage Hero",
            "class_name": "Воин",
            "level": 1,
            "route": "Frontline"
        })
        character_id = created.json()["id"]
        attack = client.post(
            f"/api/characters/{character_id}/attacks",
            headers=headers,
            json={"name": "Удар", "attack_bonus": 3, "damage": ""}
        )
        attack_id = attack.json()["id"]
        response = client.post(
            f"/api/characters/{character_id}/attacks/{attack_id}/roll-damage",
            headers=headers
        )
        assert response.status_code == 400


def test_ability_roll_returns_d20_plus_modifier_and_logs():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Ability Roller",
            "class_name": "Воин",
            "level": 1,
            "route": "Frontline",
            "strength": 16
        })
        assert created.status_code == 200, created.text
        character_id = created.json()["id"]

        response = client.post(
            f"/api/characters/{character_id}/roll-ability/strength",
            headers=headers
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["ability"] == "strength"
        assert payload["score"] == 16
        assert payload["modifier"] == 3
        assert 1 <= payload["roll"] <= 20
        assert payload["total"] == payload["roll"] + 3

        roll_messages = client.get(
            "/api/chat/messages",
            headers=headers,
            params={"channel": "rolls"}
        )
        assert roll_messages.status_code == 200, roll_messages.text
        assert any(
            "Сила" in message["content"] and message["total"] == payload["total"]
            for message in roll_messages.json()
        )


def test_ability_roll_rejects_unknown_ability():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Ability Reject Hero",
            "class_name": "Воин",
            "level": 1,
            "route": "Frontline"
        })
        character_id = created.json()["id"]
        response = client.post(
            f"/api/characters/{character_id}/roll-ability/luck",
            headers=headers
        )
        assert response.status_code == 400


def test_saving_throw_roll_returns_d20_plus_modifier_and_logs():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Save Roller",
            "class_name": "Воин",
            "level": 1,
            "route": "Frontline",
            "dexterity": 14
        })
        assert created.status_code == 200, created.text
        character_id = created.json()["id"]

        response = client.post(
            f"/api/characters/{character_id}/roll-saving-throw/dexterity",
            headers=headers
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["ability"] == "dexterity"
        assert payload["bonus"] == 2
        assert 1 <= payload["roll"] <= 20
        assert payload["total"] == payload["roll"] + 2

        roll_messages = client.get(
            "/api/chat/messages",
            headers=headers,
            params={"channel": "rolls"}
        )
        assert roll_messages.status_code == 200, roll_messages.text
        assert any(
            "Ловкость" in message["content"]
            and "спасбросок" in message["content"]
            and message["total"] == payload["total"]
            for message in roll_messages.json()
        )


def test_chat_messages_pagination_with_limit_and_before_id():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}

        for i in range(5):
            resp = client.post(
                "/api/chat/messages",
                headers=headers,
                json={"content": f"Сообщение {i + 1}"}
            )
            assert resp.status_code == 200, resp.text

        all_messages = client.get(
            "/api/chat/messages",
            headers=headers,
            params={"channel": "general", "limit": 200}
        )
        assert all_messages.status_code == 200, all_messages.text
        all_data = all_messages.json()
        assert len(all_data) == 5

        first_two = client.get(
            "/api/chat/messages",
            headers=headers,
            params={"channel": "general", "limit": 2}
        )
        assert first_two.status_code == 200, first_two.text
        page_data = first_two.json()
        assert len(page_data) == 2
        assert page_data[0]["content"] == "Сообщение 4"
        assert page_data[1]["content"] == "Сообщение 5"

        oldest_id = page_data[0]["id"]
        older = client.get(
            "/api/chat/messages",
            headers=headers,
            params={"channel": "general", "limit": 200, "before_id": oldest_id}
        )
        assert older.status_code == 200, older.text
        older_data = older.json()
        assert len(older_data) == 3
        assert all(m["id"] < oldest_id for m in older_data)
        assert older_data[0]["content"] == "Сообщение 1"
        assert older_data[1]["content"] == "Сообщение 2"
        assert older_data[2]["content"] == "Сообщение 3"

        invalid = client.get(
            "/api/chat/messages",
            headers=headers,
            params={"channel": "general", "limit": 0}
        )
        assert invalid.status_code == 422


def _register(client: TestClient, username: str) -> int:
    created = client.post("/api/users", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "secret123"
    })
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_seeded_admin_account_has_owner_role():
    with TestClient(app) as client:
        token = login(client, "admin", "admin123")
        me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        body = me.json()
        assert body["role"] == "owner"
        assert body["is_owner"] is True
        assert body["is_admin"] is True


def test_new_users_default_to_player_role():
    with TestClient(app) as client:
        _register(client, "fresh-player")
        token = login(client, "fresh-player", "secret123")
        me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        body = me.json()
        assert body["role"] == "player"
        assert body["is_admin"] is False
        assert body["is_owner"] is False


def test_owner_can_assign_roles_and_promotion_grants_admin_tools():
    with TestClient(app) as client:
        owner_token = login(client, "admin", "admin123")
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        user_id = _register(client, "promote-me")
        player_headers = {
            "Authorization": f"Bearer {login(client, 'promote-me', 'secret123')}"
        }

        # Player cannot reach admin-only endpoints before promotion.
        denied = client.get("/api/admin/users", headers=player_headers)
        assert denied.status_code == 403

        promoted = client.post(
            f"/api/admin/users/{user_id}/role",
            headers=owner_headers,
            json={"role": "admin"}
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["role"] == "admin"
        assert promoted.json()["is_admin"] is True
        assert promoted.json()["is_owner"] is False

        # After promotion the user can use the admin tools.
        allowed = client.get("/api/admin/users", headers=player_headers)
        assert allowed.status_code == 200, allowed.text
        roles = {row["username"]: row["role"] for row in allowed.json()}
        assert roles["promote-me"] == "admin"
        assert roles["admin"] == "owner"


def test_admin_role_cannot_manage_roles_only_owner_can():
    with TestClient(app) as client:
        owner_token = login(client, "admin", "admin123")
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        admin_id = _register(client, "an-admin")
        target_id = _register(client, "a-target")

        client.post(
            f"/api/admin/users/{admin_id}/role",
            headers=owner_headers,
            json={"role": "admin"}
        )
        admin_headers = {
            "Authorization": f"Bearer {login(client, 'an-admin', 'secret123')}"
        }

        # Admins keep their game-master powers (karma) ...
        karma = client.post(
            f"/api/admin/users/{target_id}/karma/add",
            headers=admin_headers,
            json={"amount": 2}
        )
        assert karma.status_code == 200, karma.text

        # ... but cannot change roles (owner only).
        forbidden = client.post(
            f"/api/admin/users/{target_id}/role",
            headers=admin_headers,
            json={"role": "admin"}
        )
        assert forbidden.status_code == 403


def test_role_endpoint_validates_role_and_blocks_self_demotion():
    with TestClient(app) as client:
        owner_token = login(client, "admin", "admin123")
        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        owner_id = client.get("/api/me", headers=owner_headers).json()["id"]

        user_id = _register(client, "role-validate")

        unknown = client.post(
            f"/api/admin/users/{user_id}/role",
            headers=owner_headers,
            json={"role": "superuser"}
        )
        assert unknown.status_code == 400

        self_demote = client.post(
            f"/api/admin/users/{owner_id}/role",
            headers=owner_headers,
            json={"role": "player"}
        )
        assert self_demote.status_code == 400

        missing = client.post(
            "/api/admin/users/999999/role",
            headers=owner_headers,
            json={"role": "admin"}
        )
        assert missing.status_code == 404


def _promote(client, owner_headers, user_id, role):
    response = client.post(
        f"/api/admin/users/{user_id}/role",
        headers=owner_headers,
        json={"role": role}
    )
    assert response.status_code == 200, response.text
    return response


def test_owner_can_appoint_head_admin_with_full_admin_tools():
    with TestClient(app) as client:
        owner_headers = {
            "Authorization": f"Bearer {login(client, 'admin', 'admin123')}"
        }

        user_id = _register(client, "deputy")
        promoted = _promote(client, owner_headers, user_id, "head_admin")
        body = promoted.json()
        assert body["role"] == "head_admin"
        assert body["is_head_admin"] is True
        assert body["is_admin"] is True
        assert body["is_owner"] is False

        head_headers = {
            "Authorization": f"Bearer {login(client, 'deputy', 'secret123')}"
        }
        me = client.get("/api/me", headers=head_headers).json()
        assert me["role"] == "head_admin"
        assert me["is_head_admin"] is True
        assert me["is_admin"] is True
        assert me["is_owner"] is False

        # Head admins have access to the game-master endpoints.
        users = client.get("/api/admin/users", headers=head_headers)
        assert users.status_code == 200, users.text


def test_head_admin_can_manage_admins_and_players():
    with TestClient(app) as client:
        owner_headers = {
            "Authorization": f"Bearer {login(client, 'admin', 'admin123')}"
        }

        head_id = _register(client, "deputy")
        target_id = _register(client, "regular")
        _promote(client, owner_headers, head_id, "head_admin")

        head_headers = {
            "Authorization": f"Bearer {login(client, 'deputy', 'secret123')}"
        }

        promoted = client.post(
            f"/api/admin/users/{target_id}/role",
            headers=head_headers,
            json={"role": "admin"}
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["role"] == "admin"

        demoted = client.post(
            f"/api/admin/users/{target_id}/role",
            headers=head_headers,
            json={"role": "player"}
        )
        assert demoted.status_code == 200, demoted.text
        assert demoted.json()["role"] == "player"


def test_head_admin_cannot_touch_owner_or_grant_privileged_roles():
    with TestClient(app) as client:
        owner_headers = {
            "Authorization": f"Bearer {login(client, 'admin', 'admin123')}"
        }
        owner_id = client.get("/api/me", headers=owner_headers).json()["id"]

        head_id = _register(client, "deputy")
        other_head_id = _register(client, "deputy-two")
        target_id = _register(client, "regular")
        _promote(client, owner_headers, head_id, "head_admin")
        _promote(client, owner_headers, other_head_id, "head_admin")

        head_headers = {
            "Authorization": f"Bearer {login(client, 'deputy', 'secret123')}"
        }

        # Cannot change the owner's role in any way.
        demote_owner = client.post(
            f"/api/admin/users/{owner_id}/role",
            headers=head_headers,
            json={"role": "player"}
        )
        assert demote_owner.status_code == 403, demote_owner.text

        # Cannot appoint a new owner.
        appoint_owner = client.post(
            f"/api/admin/users/{target_id}/role",
            headers=head_headers,
            json={"role": "owner"}
        )
        assert appoint_owner.status_code == 403, appoint_owner.text

        # Cannot grant the head-admin role (owner-only privilege).
        grant_head = client.post(
            f"/api/admin/users/{target_id}/role",
            headers=head_headers,
            json={"role": "head_admin"}
        )
        assert grant_head.status_code == 403, grant_head.text

        # Cannot change another head admin's role.
        touch_head = client.post(
            f"/api/admin/users/{other_head_id}/role",
            headers=head_headers,
            json={"role": "admin"}
        )
        assert touch_head.status_code == 403, touch_head.text

        # The owner is untouched and the targets keep their roles.
        owner_me = client.get("/api/me", headers=owner_headers).json()
        assert owner_me["role"] == "owner"


def test_owner_can_revoke_head_admin_role():
    with TestClient(app) as client:
        owner_headers = {
            "Authorization": f"Bearer {login(client, 'admin', 'admin123')}"
        }

        head_id = _register(client, "deputy")
        _promote(client, owner_headers, head_id, "head_admin")

        revoked = _promote(client, owner_headers, head_id, "player")
        assert revoked.json()["role"] == "player"
        assert revoked.json()["is_head_admin"] is False
        assert revoked.json()["is_admin"] is False


def test_migrate_user_roles_uses_boolean_true_comparison():
    """migrate_user_roles must compare is_admin with TRUE, not 1.

    PostgreSQL rejects ``is_admin = 1`` on a boolean column, so the
    comparison must use ``is_admin = TRUE`` to be compatible with both
    PostgreSQL and SQLite.
    """
    from sqlalchemy import text
    from app.db.database import engine
    from app.main import migrate_user_roles
    from app.core.roles import Role

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS users"))
        conn.execute(text(
            "CREATE TABLE users ("
            "  id INTEGER PRIMARY KEY,"
            "  username TEXT NOT NULL,"
            "  email TEXT NOT NULL,"
            "  hashed_password TEXT NOT NULL,"
            "  karma INTEGER NOT NULL DEFAULT 0,"
            "  is_admin BOOLEAN NOT NULL DEFAULT 0"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO users (id, username, email, hashed_password, is_admin) VALUES "
            "(1, 'legacy-admin', 'la@example.com', 'x', TRUE),"
            "(2, 'legacy-player', 'lp@example.com', 'x', FALSE)"
        ))

    migrate_user_roles()

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT username, role FROM users ORDER BY id")
        ).fetchall()

    assert rows[0] == ("legacy-admin", Role.ADMIN), (
        "Legacy admin with is_admin=TRUE should be migrated to 'admin' role"
    )
    assert rows[1] == ("legacy-player", Role.PLAYER), (
        "Legacy player with is_admin=FALSE should be migrated to 'player' role"
    )


# ---------------------------------------------------------------------------
# Game calendar / free-day tracking
# ---------------------------------------------------------------------------

from datetime import timedelta

from app.core.calendar import GAME_EPOCH


def _make_character(client, headers, **overrides):
    payload = {
        "name": "Calendar Hero",
        "class_name": "Wizard",
        "level": 1,
        "route": "Market",
        "investigation": 20,
    }
    payload.update(overrides)
    created = client.post("/api/characters", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    return created.json()


def test_character_defaults_to_game_epoch_creation_date():
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {login(client, 'admin', 'admin123')}"}
        character = _make_character(client, headers)
        assert character["game_created_at"] == GAME_EPOCH.isoformat()


def test_character_accepts_custom_creation_date():
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {login(client, 'admin', 'admin123')}"}
        character = _make_character(client, headers, game_created_at="2025-09-15")
        assert character["game_created_at"] == "2025-09-15"


def test_character_rejects_creation_date_before_epoch():
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {login(client, 'admin', 'admin123')}"}
        created = client.post("/api/characters", headers=headers, json={
            "name": "Too Early",
            "class_name": "Wizard",
            "level": 1,
            "route": "Market",
            "game_created_at": "2025-05-31",
        })
        assert created.status_code == 400, created.text


def test_calendar_summary_reports_total_busy_and_free_days():
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {login(client, 'admin', 'admin123')}"}
        character = _make_character(client, headers)
        cid = character["id"]

        summary = client.get(
            f"/api/characters/{cid}/calendar", headers=headers
        ).json()
        assert summary["created_at"] == GAME_EPOCH.isoformat()
        assert summary["busy_days"] == 0
        assert summary["free_days"] == summary["total_days"]
        assert summary["total_days"] > 0


def test_manual_downtime_entry_reduces_free_days():
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {login(client, 'admin', 'admin123')}"}
        cid = _make_character(client, headers)["id"]

        response = client.post(
            f"/api/characters/{cid}/calendar/downtime",
            headers=headers,
            json={"start_date": "2025-06-01", "days": 5, "reason": "Крафт"},
        )
        assert response.status_code == 200, response.text
        summary = response.json()
        assert summary["busy_days"] == 5
        assert summary["free_days"] == summary["total_days"] - 5
        assert len(summary["entries"]) == 1
        assert summary["entries"][0]["source"] == "manual"
        assert summary["entries"][0]["reason"] == "Крафт"


def test_manual_downtime_cannot_start_before_creation_date():
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {login(client, 'admin', 'admin123')}"}
        cid = _make_character(client, headers, game_created_at="2025-09-15")["id"]

        rejected = client.post(
            f"/api/characters/{cid}/calendar/downtime",
            headers=headers,
            json={"start_date": "2025-09-10", "days": 1, "reason": "Слишком рано"},
        )
        assert rejected.status_code == 400, rejected.text

        accepted = client.post(
            f"/api/characters/{cid}/calendar/downtime",
            headers=headers,
            json={"start_date": "2025-09-20", "days": 1, "reason": "Норм"},
        )
        assert accepted.status_code == 200, accepted.text


def test_manual_downtime_rejects_non_positive_days():
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {login(client, 'admin', 'admin123')}"}
        cid = _make_character(client, headers)["id"]
        rejected = client.post(
            f"/api/characters/{cid}/calendar/downtime",
            headers=headers,
            json={"start_date": "2025-06-01", "days": 0, "reason": "Ничего"},
        )
        assert rejected.status_code == 400, rejected.text


def test_downtime_entry_can_be_deleted():
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {login(client, 'admin', 'admin123')}"}
        cid = _make_character(client, headers)["id"]
        summary = client.post(
            f"/api/characters/{cid}/calendar/downtime",
            headers=headers,
            json={"start_date": "2025-06-01", "days": 3, "reason": "Крафт"},
        ).json()
        entry_id = summary["entries"][0]["id"]

        deleted = client.delete(
            f"/api/characters/{cid}/calendar/downtime/{entry_id}",
            headers=headers,
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["busy_days"] == 0
        assert deleted.json()["entries"] == []


def test_shop_search_spends_oldest_free_days_first():
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {login(client, 'admin', 'admin123')}"}
        cid = _make_character(client, headers)["id"]
        client.post(
            f"/api/admin/characters/{cid}/currency/add",
            headers=headers,
            json={"gold": 10000, "silver": 0, "copper": 0},
        )

        search = client.post(
            f"/api/characters/{cid}/shop/search",
            headers=headers,
            json={
                "mode": "buy",
                "item_name": "Healing Potion",
                "rarity": "Обычный",
                "is_consumable": True,
                "searcher_type": "character",
            },
        )
        assert search.status_code == 200, search.text
        spent_days = search.json()["days"]
        assert spent_days > 0

        summary = client.get(
            f"/api/characters/{cid}/calendar", headers=headers
        ).json()
        assert summary["busy_days"] == spent_days
        # Oldest days are spent first, so the run begins at the game epoch.
        shop_entries = [e for e in summary["entries"] if e["source"] == "shop"]
        assert shop_entries
        assert shop_entries[0]["start_date"] == GAME_EPOCH.isoformat()


def test_shop_search_blocked_when_not_enough_free_days():
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {login(client, 'admin', 'admin123')}"}
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        cid = _make_character(
            client, headers, game_created_at=yesterday
        )["id"]
        client.post(
            f"/api/admin/characters/{cid}/currency/add",
            headers=headers,
            json={"gold": 10000, "silver": 0, "copper": 0},
        )
        # Occupy the single available free day so none remain.
        client.post(
            f"/api/characters/{cid}/calendar/downtime",
            headers=headers,
            json={"start_date": yesterday, "days": 1, "reason": "Занят"},
        )

        search = client.post(
            f"/api/characters/{cid}/shop/search",
            headers=headers,
            json={
                "mode": "buy",
                "item_name": "Healing Potion",
                "rarity": "Обычный",
                "is_consumable": True,
                "searcher_type": "character",
            },
        )
        assert search.status_code == 400, search.text
        assert "свободных дней" in search.json()["detail"]

        # The blocked search must not have charged gold.
        inventory = client.get(
            f"/api/characters/{cid}/inventory", headers=headers
        ).json()
        assert inventory["gold"] == 10000


# ---------------------------------------------------------------------------
# Calendar permissions and audit log (issue #51)
# ---------------------------------------------------------------------------

def _make_player_with_character(client, username, character_name="Calendar Hero"):
    """Create a player account + one character, returning (headers, character_id)."""
    created = client.post("/api/users", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "secret123",
    })
    assert created.status_code == 200, created.text
    token = login(client, username, "secret123")
    headers = {"Authorization": f"Bearer {token}"}
    character = client.post("/api/characters", headers=headers, json={
        "name": character_name,
        "class_name": "Wizard",
        "level": 3,
        "route": "Arcane",
    })
    assert character.status_code == 200, character.text
    return headers, character.json()["id"]


def _add_downtime(client, headers, character_id, start="2025-06-01", days=3, reason="Крафт"):
    response = client.post(
        f"/api/characters/{character_id}/calendar/downtime",
        headers=headers,
        json={"start_date": start, "days": days, "reason": reason},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_player_can_add_and_view_but_cannot_edit_or_delete_downtime():
    with TestClient(app) as client:
        headers, cid = _make_player_with_character(client, "calendar-player")

        summary = _add_downtime(client, headers, cid)
        assert summary["busy_days"] == 3
        assert summary["can_manage"] is False
        assert len(summary["entries"]) == 1
        entry_id = summary["entries"][0]["id"]

        # Viewing is allowed and reports the player cannot manage entries.
        view = client.get(f"/api/characters/{cid}/calendar", headers=headers)
        assert view.status_code == 200, view.text
        assert view.json()["can_manage"] is False

        # Editing is forbidden for players.
        edited = client.patch(
            f"/api/characters/{cid}/calendar/downtime/{entry_id}",
            headers=headers,
            json={"days": 1},
        )
        assert edited.status_code == 403, edited.text

        # Deleting is forbidden for players.
        deleted = client.delete(
            f"/api/characters/{cid}/calendar/downtime/{entry_id}",
            headers=headers,
        )
        assert deleted.status_code == 403, deleted.text

        # The entry must still be intact after the rejected attempts.
        view = client.get(f"/api/characters/{cid}/calendar", headers=headers)
        assert len(view.json()["entries"]) == 1
        assert view.json()["entries"][0]["days"] == 3


def test_admin_can_add_edit_and_delete_any_character_downtime():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        player_headers, cid = _make_player_with_character(client, "managed-player")

        # Admin adds downtime to another player's character.
        added = client.post(
            f"/api/characters/{cid}/calendar/downtime",
            headers=admin_headers,
            json={"start_date": "2025-06-01", "days": 2, "reason": "Исправление"},
        )
        assert added.status_code == 200, added.text
        assert added.json()["can_manage"] is True
        entry_id = added.json()["entries"][0]["id"]

        # Admin edits the entry.
        edited = client.patch(
            f"/api/characters/{cid}/calendar/downtime/{entry_id}",
            headers=admin_headers,
            json={"days": 5, "reason": "Скорректировано"},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["entries"][0]["days"] == 5
        assert edited.json()["entries"][0]["reason"] == "Скорректировано"

        # Admin deletes the entry.
        deleted = client.delete(
            f"/api/characters/{cid}/calendar/downtime/{entry_id}",
            headers=admin_headers,
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["entries"] == []

        # The player can still see their (now empty) calendar.
        view = client.get(f"/api/characters/{cid}/calendar", headers=player_headers)
        assert view.status_code == 200, view.text
        assert view.json()["entries"] == []


def test_calendar_admin_actions_are_recorded_in_audit_log():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        player_headers, cid = _make_player_with_character(
            client, "audited-player", character_name="Audited Hero"
        )

        # A player's own add must NOT be audited (only admin corrections are).
        _add_downtime(client, player_headers, cid, days=2)

        logs = client.get("/api/admin/calendar-logs", headers=admin_headers)
        assert logs.status_code == 200, logs.text
        assert logs.json() == []

        # Admin create / update / delete are all audited.
        created = client.post(
            f"/api/characters/{cid}/calendar/downtime",
            headers=admin_headers,
            json={"start_date": "2025-07-01", "days": 1, "reason": "Аудит"},
        )
        entry_id = created.json()["entries"][-1]["id"]
        client.patch(
            f"/api/characters/{cid}/calendar/downtime/{entry_id}",
            headers=admin_headers,
            json={"days": 2},
        )
        client.delete(
            f"/api/characters/{cid}/calendar/downtime/{entry_id}",
            headers=admin_headers,
        )

        logs = client.get("/api/admin/calendar-logs", headers=admin_headers)
        assert logs.status_code == 200, logs.text
        actions = [row["action"] for row in logs.json()]
        assert sorted(actions) == ["create", "delete", "update"]
        for row in logs.json():
            assert row["username"] == "admin"
            assert row["character_id"] == cid
            assert row["character_name"] == "Audited Hero"
            assert row["details"]

        # The audit log can be filtered by action and character.
        deletes = client.get(
            "/api/admin/calendar-logs",
            headers=admin_headers,
            params={"action": "delete", "character_id": cid},
        )
        assert deletes.status_code == 200, deletes.text
        assert len(deletes.json()) == 1
        assert deletes.json()[0]["action"] == "delete"


def test_calendar_logs_require_admin():
    with TestClient(app) as client:
        player_headers, _ = _make_player_with_character(client, "nosy-player")
        forbidden = client.get("/api/admin/calendar-logs", headers=player_headers)
        assert forbidden.status_code == 403, forbidden.text
