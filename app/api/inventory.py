import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.character import Character
from app.models.inventory import Inventory, InventoryItem, ShopQuote, ShopTransactionLog, TransferLog
from app.models.user import User
from app.api.calendar import charge_character_downtime
from app.api.users import get_current_user
from app.schemas.inventory import (
    AddItemRequest,
    CurrencyTransferRequest,
    CurrencyUpdateRequest,
    GoldUpdateRequest,
    InventoryResponse,
    InventoryNotesUpdateRequest,
    ItemTransferRequest,
    MagicItemResponse,
    ShopConfirmRequest,
    ShopResult,
    ShopSearchRequest,
)
import random


router = APIRouter()

RARITY_DATA = {
    "Обычный": {"dc": 5, "days_dice": 4, "base_price": 100},
    "Необычный": {"dc": 10, "days_dice": 8, "base_price": 500},
    "Редкий": {"dc": 15, "days_dice": 12, "base_price": 5000},
}

CONSUMABLE_BASE_PRICE = {
    "Обычный": 50,
    "Необычный": 250,
    "Редкий": 2500,
}

RARITY_PRICE_ROLL_MODIFIER = {
    "Обычный": 10,
    "Необычный": 0,
    "Редкий": -10,
}

HIRELING_BONUSES = {
    "Плохой": 0,
    "Хороший": 4,
    "Компетентный": 6,
    "Эксперт": 8,
}

HIRELING_DAILY_COST = {
    "Плохой": 1,
    "Хороший": 5,
    "Компетентный": 10,
    "Эксперт": 25,
}

HIRELING_ALIASES = {
    "Опытный": "Компетентный",
    "Экспертный": "Эксперт",
}

MAGIC_VARIANTS_PATH = Path(__file__).resolve().parents[2] / "magicvariants.json"
MAGIC_ITEM_RARITY_LABELS = {
    "common": "Обычный",
    "uncommon": "Необычный",
    "rare": "Редкий",
}
MAGIC_ITEM_RARITY_FILTERS = {
    key.casefold(): key
    for key in MAGIC_ITEM_RARITY_LABELS
} | {
    value.casefold(): key
    for key, value in MAGIC_ITEM_RARITY_LABELS.items()
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_character_inventory(
    character_id: int,
    current_user: User,
    db: Session
) -> Inventory:
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.user_id == current_user.id
    ).first()

    if not character:
        raise HTTPException(
            status_code=404,
            detail="Character not found"
        )

    inventory = db.query(Inventory).filter(
        Inventory.character_id == character_id
    ).first()

    if not inventory:
        inventory = Inventory(
            character_id=character_id,
            gold=0,
            silver=0,
            copper=0,
            notes=""
        )
        db.add(inventory)
        db.commit()
        db.refresh(inventory)

    return inventory

def get_or_create_inventory_for_character(character: Character, db: Session) -> Inventory:
    inventory = db.query(Inventory).filter(
        Inventory.character_id == character.id
    ).first()

    if not inventory:
        inventory = Inventory(
            character_id=character.id,
            gold=0,
            silver=0,
            copper=0,
            notes=""
        )
        db.add(inventory)
        db.flush()

    return inventory

def validate_rarity(rarity: str):
    if rarity not in RARITY_DATA:
        raise HTTPException(
            status_code=400,
            detail="Unknown rarity"
        )

def require_inventory_grant_admin(current_user: User):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Admin permissions required"
        )

def get_inventory_for_admin_grant(character_id: int, db: Session) -> Inventory:
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(
            status_code=404,
            detail="Character not found"
        )
    return get_or_create_inventory_for_character(character, db)


def normalize_catalog_text(value: str) -> str:
    return " ".join(value.casefold().split())


KNOWN_UNAVAILABLE_MAGIC_ITEM_NAMES = {
    normalize_catalog_text("Vorpal Sword"),
}


def raw_magic_item_rarity(record: dict) -> str:
    inherits = record.get("inherits") or {}
    rarity = inherits.get("rarity") or record.get("rarity") or ""
    return rarity.strip().casefold()


def magic_item_source_value(record: dict, key: str):
    inherits = record.get("inherits") or {}
    return record.get(key) or inherits.get(key)


def describe_magic_item_type(record: dict) -> str:
    if record.get("ammo"):
        return "Боеприпас"

    requires = record.get("requires") or []
    if any(requirement.get("armor") or requirement.get("type") in {"LA", "MA", "HA"} for requirement in requires):
        return "Доспех"
    if any(requirement.get("type") == "S" for requirement in requires):
        return "Щит"
    if any(
        requirement.get("type") in {"A", "AF|DMG"} or requirement.get("arrow") or requirement.get("bolt")
        for requirement in requires
    ):
        return "Боеприпас"
    if any(
        requirement.get("weapon")
        or requirement.get("weaponCategory")
        or requirement.get("sword")
        or requirement.get("bow")
        or requirement.get("axe")
        or requirement.get("net")
        or requirement.get("crossbow")
        or requirement.get("spear")
        or requirement.get("polearm")
        or requirement.get("type") == "M"
        for requirement in requires
    ):
        return "Оружие"
    if any(requirement.get("type") == "SCF" for requirement in requires):
        return "Фокусировка"

    return magic_item_source_value(record, "type") or "Магический предмет"


def magic_item_entries(record: dict) -> list[str]:
    entries = []
    for source in (record, record.get("inherits") or {}):
        for entry in source.get("entries") or []:
            if isinstance(entry, str):
                entries.append(entry)
    return entries[:3]


def serialize_magic_variant(index: int, record: dict) -> dict:
    rarity_key = raw_magic_item_rarity(record)
    name = record.get("name") or magic_item_source_value(record, "name")
    return {
        "id": f"magicvariant-{index}",
        "name": name,
        "rarity": MAGIC_ITEM_RARITY_LABELS.get(rarity_key, rarity_key),
        "rarity_key": rarity_key,
        "item_type": describe_magic_item_type(record),
        "source": magic_item_source_value(record, "source"),
        "page": magic_item_source_value(record, "page"),
        "tier": magic_item_source_value(record, "tier"),
        "is_consumable": bool(record.get("ammo")),
        "reference_sources": record.get("referenceSources") or [],
        "requires": record.get("requires") or [],
        "entries": magic_item_entries(record),
        "available": rarity_key in MAGIC_ITEM_RARITY_LABELS
    }


@lru_cache
def load_magic_variants() -> tuple[dict, ...]:
    with MAGIC_VARIANTS_PATH.open(encoding="utf-8") as catalog_file:
        data = json.load(catalog_file)
    return tuple(
        record
        for record in data.get("magicvariant", [])
        if record.get("name") or magic_item_source_value(record, "name")
    )


@lru_cache
def all_magic_items_by_id() -> dict[str, dict]:
    return {
        item["id"]: item
        for item in (
            serialize_magic_variant(index, record)
            for index, record in enumerate(load_magic_variants())
        )
    }


@lru_cache
def all_magic_items_by_name() -> dict[str, dict]:
    return {
        normalize_catalog_text(item["name"]): item
        for item in all_magic_items_by_id().values()
    }


@lru_cache
def available_magic_items() -> tuple[dict, ...]:
    return tuple(
        sorted(
            (
                {key: value for key, value in item.items() if key != "available"}
                for item in all_magic_items_by_id().values()
                if item["available"]
            ),
            key=lambda item: item["name"].casefold()
        )
    )


def catalog_rarity_filter_key(rarity: str | None) -> str | None:
    if not rarity:
        return None
    rarity_key = MAGIC_ITEM_RARITY_FILTERS.get(rarity.strip().casefold())
    if not rarity_key:
        raise HTTPException(
            status_code=400,
            detail="Unknown rarity"
        )
    return rarity_key


def require_available_magic_item(item: dict | None) -> dict:
    if not item or not item["available"]:
        raise HTTPException(
            status_code=400,
            detail="Magic item is not available in the shop"
        )
    return item


def selected_magic_item_payload(item: dict, mode: str) -> dict:
    return {
        "mode": mode,
        "item_name": item["name"],
        "rarity": item["rarity"],
        "is_consumable": item["is_consumable"],
        "item_id": None
    }


def require_non_negative_currency(currency: CurrencyUpdateRequest):
    if currency.gold < 0 or currency.silver < 0 or currency.copper < 0:
        raise HTTPException(
            status_code=400,
            detail="Currency amounts must not be negative"
        )
def require_positive_currency(currency: CurrencyUpdateRequest):
    require_non_negative_currency(currency)
    if currency.gold == 0 and currency.silver == 0 and currency.copper == 0:
        raise HTTPException(
            status_code=400,
            detail="Transfer amount must be positive"
        )
def inventory_total_copper(inventory: Inventory) -> int:
    return inventory.gold * 100 + inventory.silver * 10 + inventory.copper

def set_inventory_from_copper(inventory: Inventory, amount: int):
    inventory.gold = amount // 100
    amount %= 100
    inventory.silver = amount // 10
    inventory.copper = amount % 10

def add_currency(inventory: Inventory, gold: int = 0, silver: int = 0, copper: int = 0):
    set_inventory_from_copper(
        inventory,
        max(
            0,
            inventory_total_copper(inventory) + gold * 100 + silver * 10 + copper
        )
    )

def record_currency_transfer(
    sender: Character,
    recipient: Character,
    transfer_data: CurrencyTransferRequest,
    user: User,
    db: Session
):
    db.add(TransferLog(
        user_id=user.id,
        username=user.username,
        sender_character_id=sender.id,
        sender_character_name=sender.name,
        recipient_character_id=recipient.id,
        recipient_character_name=recipient.name,
        transfer_type="currency",
        gold=transfer_data.gold,
        silver=transfer_data.silver,
        copper=transfer_data.copper
    ))

def record_item_transfer(
    sender: Character,
    recipient: Character,
    item: InventoryItem,
    user: User,
    db: Session
):
    db.add(TransferLog(
        user_id=user.id,
        username=user.username,
        sender_character_id=sender.id,
        sender_character_name=sender.name,
        recipient_character_id=recipient.id,
        recipient_character_name=recipient.name,
        transfer_type="item",
        item_name=item.name,
        item_rarity=item.rarity,
        item_is_consumable=item.is_consumable
    ))

def subtract_copper(inventory: Inventory, amount: int, detail: str):
    current_amount = inventory_total_copper(inventory)
    if current_amount < amount:
        raise HTTPException(
            status_code=400,
            detail=detail
        )
    set_inventory_from_copper(inventory, current_amount - amount)

def subtract_gold_amount(inventory: Inventory, amount: int, detail: str):
    if amount < 0:
        raise HTTPException(
            status_code=400,
            detail="Gold amount must not be negative"
        )
    subtract_copper(inventory, amount * 100, detail)

def base_price_for_item(rarity: str, is_consumable: bool) -> int:
    validate_rarity(rarity)
    if is_consumable:
        return CONSUMABLE_BASE_PRICE[rarity]
    return RARITY_DATA[rarity]["base_price"]

def adjusted_price_roll(rarity: str) -> int:
    price_roll = random.randint(1, 100) + RARITY_PRICE_ROLL_MODIFIER[rarity]
    return max(1, min(100, price_roll))

def roll_buy_price_multiplier(rarity: str):
    price_roll = adjusted_price_roll(rarity)
    if price_roll <= 20:
        multiplier = 1.5 + (random.randint(0, 500) / 1000)
    elif price_roll <= 40:
        multiplier = 1.0 + (random.randint(0, 490) / 1000)
    elif price_roll <= 80:
        multiplier = 0.75 + (random.randint(0, 240) / 1000)
    elif price_roll <= 90:
        multiplier = 0.5 + (random.randint(0, 240) / 1000)
    else:
        multiplier = 0.5 - (random.randint(0, 200) / 1000)
    return price_roll, multiplier


def roll_sell_price_multiplier(rarity: str):
    price_roll = adjusted_price_roll(rarity)
    if price_roll <= 20:
        multiplier = 0.5 - (random.randint(0, 200) / 1000)
    elif price_roll <= 42:
        multiplier = 0.5 + (random.randint(0, 250) / 1000)
    elif price_roll <= 82:
        multiplier = 0.75 + (random.randint(0, 150) / 1000)
    elif price_roll <= 92:
        multiplier = 0.9 + (random.randint(0, 350) / 1000)
    else:
        multiplier = 1.25 + (random.randint(0, 350) / 1000)
    return price_roll, multiplier

def canonical_hireling_level(level: str) -> str:
    return HIRELING_ALIASES.get(level, level)

def search_item(
    character: Character,
    rarity: str,
    searcher_type: str,
    hireling_level: str
):
    validate_rarity(rarity)
    rarity_data = RARITY_DATA[rarity]

    if searcher_type == "character":
        modifier = character.investigation
        daily_cost = 0
    elif searcher_type == "hireling":
        normalized_level = canonical_hireling_level(hireling_level)
        if normalized_level not in HIRELING_BONUSES:
            raise HTTPException(
                status_code=400,
                detail="Unknown hireling level"
            )
        modifier = HIRELING_BONUSES[normalized_level]
        daily_cost = HIRELING_DAILY_COST[normalized_level]
    else:
        raise HTTPException(
            status_code=400,
            detail="Unknown searcher type"
        )

    search_roll = random.randint(1, 20)
    total_roll = search_roll + modifier
    success = total_roll >= rarity_data["dc"]
    if success:
        days = random.randint(1, rarity_data["days_dice"])
    else:
        days = rarity_data["days_dice"]

    return {
        "success": success,
        "search_roll": search_roll,
        "modifier": modifier,
        "total_roll": total_roll,
        "dc": rarity_data["dc"],
        "days": days,
        "hireling_cost": days * daily_cost
    }

def get_character_for_current_user(
    character_id: int,
    current_user: User,
    db: Session
) -> Character:
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.user_id == current_user.id
    ).first()

    if not character:
        raise HTTPException(
            status_code=404,
            detail="Персонаж не найден"
        )

    return character

def resolve_search_item(
    inventory: Inventory,
    search_data: ShopSearchRequest,
    db: Session
):
    mode = search_data.mode
    if mode == "buy":
        if search_data.magic_item_id:
            item = require_available_magic_item(
                all_magic_items_by_id().get(search_data.magic_item_id)
            )
            return selected_magic_item_payload(item, mode)

        if not search_data.item_name or not search_data.rarity:
            raise HTTPException(
                status_code=400,
                detail="Item name and rarity are required"
            )

        normalized_item_name = normalize_catalog_text(search_data.item_name)
        if normalized_item_name in KNOWN_UNAVAILABLE_MAGIC_ITEM_NAMES:
            raise HTTPException(
                status_code=400,
                detail="Magic item is not available in the shop"
            )

        catalog_item = all_magic_items_by_name().get(normalized_item_name)
        if catalog_item:
            item = require_available_magic_item(catalog_item)
            return selected_magic_item_payload(item, mode)

        validate_rarity(search_data.rarity)
        return {
            "mode": mode,
            "item_name": search_data.item_name,
            "rarity": search_data.rarity,
            "is_consumable": search_data.is_consumable,
            "item_id": None
        }

    if mode == "sell":
        if search_data.item_id is None:
            raise HTTPException(
                status_code=400,
                detail="Item id is required for selling"
            )
        item = db.query(InventoryItem).filter(
            InventoryItem.id == search_data.item_id,
            InventoryItem.inventory_id == inventory.id
        ).first()
        if not item:
            raise HTTPException(
                status_code=400,
                detail="Предмета нет в инвентаре"
            )
        validate_rarity(item.rarity)
        return {
            "mode": mode,
            "item_name": item.name,
            "rarity": item.rarity,
            "is_consumable": item.is_consumable,
            "item_id": item.id
        }

    raise HTTPException(
        status_code=400,
        detail="Unknown shop mode"
    )

def quote_total_cost(quote: ShopQuote) -> int:
    if quote.mode == "buy" and quote.item_price is not None:
        return quote.hireling_cost + quote.item_price
    return quote.hireling_cost

def serialize_quote(quote: ShopQuote, inventory: Inventory):
    return {
        "quote_id": quote.id,
        "mode": quote.mode,
        "item_name": quote.item_name,
        "rarity": quote.rarity,
        "is_consumable": quote.is_consumable,
        "success": quote.success,
        "search_roll": quote.search_roll,
        "modifier": quote.modifier,
        "total_roll": quote.total_roll,
        "dc": quote.dc,
        "days": quote.days,
        "hireling_cost": quote.hireling_cost,
        "price_roll": quote.price_roll,
        "multiplier": quote.multiplier,
        "item_price": quote.item_price,
        "total_cost": quote_total_cost(quote),
        "is_consumed": quote.is_consumed,
        "inventory": inventory
    }

def get_quote_for_inventory(
    inventory: Inventory,
    quote_id: int,
    db: Session
) -> ShopQuote:
    quote = db.query(ShopQuote).filter(
        ShopQuote.id == quote_id,
        ShopQuote.inventory_id == inventory.id
    ).first()
    if not quote:
        raise HTTPException(
            status_code=404,
            detail="Shop result not found"
        )
    if quote.is_consumed:
        raise HTTPException(
            status_code=400,
            detail="Shop result has already been used"
        )
    if not quote.success or quote.item_price is None:
        raise HTTPException(
            status_code=400,
            detail="Search did not find a valid deal"
        )
    return quote

def record_shop_transaction(
    quote: ShopQuote,
    character: Character,
    inventory: Inventory,
    user: User,
    db: Session
):
    if quote.item_price is None:
        raise HTTPException(
            status_code=400,
            detail="Search did not find a valid deal"
        )

    if quote.mode == "buy":
        total_amount = quote.item_price + quote.hireling_cost
    else:
        total_amount = quote.item_price - quote.hireling_cost

    db.add(ShopTransactionLog(
        user_id=user.id,
        username=user.username,
        character_id=character.id,
        character_name=character.name,
        inventory_id=inventory.id,
        mode=quote.mode,
        item_name=quote.item_name,
        rarity=quote.rarity,
        item_price=quote.item_price,
        hireling_cost=quote.hireling_cost,
        total_amount=total_amount
    ))


@router.get("/shop/magic-items", response_model=list[MagicItemResponse])
def list_magic_items(
    search: str | None = None,
    rarity: str | None = None,
    item_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    _: User = Depends(get_current_user)
):
    rarity_key = catalog_rarity_filter_key(rarity)
    search_text = normalize_catalog_text(search or "")
    item_type_text = normalize_catalog_text(item_type or "")

    items = []
    for item in available_magic_items():
        if search_text and search_text not in normalize_catalog_text(item["name"]):
            continue
        if rarity_key and item["rarity_key"] != rarity_key:
            continue
        if item_type_text and item_type_text not in normalize_catalog_text(item["item_type"]):
            continue
        items.append(item)
        if len(items) >= limit:
            break

    return items


@router.get("/characters/{character_id}/inventory", response_model=InventoryResponse)
def get_inventory(
    character_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inventory = get_character_inventory(character_id, current_user, db)
    return inventory


@router.post("/characters/{character_id}/inventory/items", response_model=InventoryResponse)
def add_item(
    character_id: int,
    item_data: AddItemRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_inventory_grant_admin(current_user)
    validate_rarity(item_data.rarity)
    inventory = get_inventory_for_admin_grant(character_id, db)

    item = InventoryItem(
        name=item_data.name,
        rarity=item_data.rarity,
        is_consumable=item_data.is_consumable,
        inventory_id=inventory.id
    )
    db.add(item)
    db.commit()
    db.refresh(inventory)

    return inventory


@router.patch("/characters/{character_id}/inventory/notes", response_model=InventoryResponse)
def update_inventory_notes(
    character_id: int,
    notes_data: InventoryNotesUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inventory = get_character_inventory(character_id, current_user, db)
    inventory.notes = notes_data.notes
    db.commit()
    db.refresh(inventory)

    return inventory


@router.delete("/characters/{character_id}/inventory/items/{item_id}", response_model=InventoryResponse)
def remove_item(
    character_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    inventory = get_character_inventory(character_id, current_user, db)

    item = db.query(InventoryItem).filter(
        InventoryItem.id == item_id,
        InventoryItem.inventory_id == inventory.id
    ).first()

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Предмет не найден"
        )

    db.delete(item)
    db.commit()
    db.refresh(inventory)

    return inventory


@router.post("/characters/{character_id}/inventory/gold/add", response_model=InventoryResponse)
def add_gold(
    character_id: int,
    gold_data: GoldUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_inventory_grant_admin(current_user)
    if gold_data.amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Amount must be positive"
        )

    inventory = get_inventory_for_admin_grant(character_id, db)

    inventory.gold += gold_data.amount
    db.commit()
    db.refresh(inventory)

    return inventory


@router.post("/characters/{character_id}/inventory/gold/subtract", response_model=InventoryResponse)
def subtract_gold(
    character_id: int,
    gold_data: GoldUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if gold_data.amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Число должно быть положительным"
        )

    inventory = get_character_inventory(character_id, current_user, db)

    if inventory.gold < gold_data.amount:
        raise HTTPException(
            status_code=400,
            detail="Недостаточно денег"
        )

    inventory.gold -= gold_data.amount
    db.commit()
    db.refresh(inventory)

    return inventory

@router.post("/characters/{character_id}/inventory/currency/add", response_model=InventoryResponse)
def add_inventory_currency(
    character_id: int,
    currency_data: CurrencyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_inventory_grant_admin(current_user)
    require_non_negative_currency(currency_data)
    inventory = get_inventory_for_admin_grant(character_id, db)
    add_currency(
        inventory,
        currency_data.gold,
        currency_data.silver,
        currency_data.copper
    )
    db.commit()
    db.refresh(inventory)

    return inventory

@router.post("/characters/{character_id}/inventory/currency/transfer", response_model=InventoryResponse)
def transfer_inventory_currency(
    character_id: int,
    transfer_data: CurrencyTransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_positive_currency(transfer_data)
    sender = get_character_for_current_user(character_id, current_user, db)
    if sender.id == transfer_data.recipient_character_id:
        raise HTTPException(
            status_code=400,
            detail="Recipient must be a different character"
        )

    recipient = db.query(Character).filter(
        Character.id == transfer_data.recipient_character_id
    ).first()
    if not recipient:
        raise HTTPException(
            status_code=404,
            detail="Recipient character not found"
        )

    sender_inventory = get_or_create_inventory_for_character(sender, db)
    recipient_inventory = get_or_create_inventory_for_character(recipient, db)
    amount = transfer_data.gold * 100 + transfer_data.silver * 10 + transfer_data.copper
    subtract_copper(sender_inventory, amount, "Недостаточно средств")
    add_currency(
        recipient_inventory,
        transfer_data.gold,
        transfer_data.silver,
        transfer_data.copper
    )
    record_currency_transfer(sender, recipient, transfer_data, current_user, db)
    db.commit()
    db.refresh(sender_inventory)

    return sender_inventory

@router.post("/characters/{character_id}/inventory/items/transfer", response_model=InventoryResponse)
def transfer_inventory_item(
    character_id: int,
    transfer_data: ItemTransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sender = get_character_for_current_user(character_id, current_user, db)
    if sender.id == transfer_data.recipient_character_id:
        raise HTTPException(
            status_code=400,
            detail="Recipient must be a different character"
        )

    recipient = db.query(Character).filter(
        Character.id == transfer_data.recipient_character_id
    ).first()
    if not recipient:
        raise HTTPException(
            status_code=404,
            detail="Recipient character not found"
        )

    sender_inventory = get_or_create_inventory_for_character(sender, db)
    recipient_inventory = get_or_create_inventory_for_character(recipient, db)
    item = db.query(InventoryItem).filter(
        InventoryItem.id == transfer_data.item_id,
        InventoryItem.inventory_id == sender_inventory.id
    ).first()
    if not item:
        raise HTTPException(
            status_code=400,
            detail="Предмета нет в инвентаре"
        )

    record_item_transfer(sender, recipient, item, current_user, db)
    item.inventory_id = recipient_inventory.id
    db.commit()
    db.refresh(sender_inventory)

    return sender_inventory

@router.post("/characters/{character_id}/shop/search", response_model=ShopResult)
def search_shop_item(
    character_id: int,
    search_data: ShopSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    character = get_character_for_current_user(character_id, current_user, db)
    inventory = get_character_inventory(character_id, current_user, db)
    item_data = resolve_search_item(inventory, search_data, db)
    search_result = search_item(
        character,
        item_data["rarity"],
        search_data.searcher_type,
        search_data.hireling_level
    )

    # Searching the market consumes in-world time. Spend the character's
    # oldest free days first (raising 400 if there are not enough) before
    # charging gold, so a failed time check leaves the inventory untouched.
    mode_label = "покупателя" if item_data["mode"] == "sell" else "продавца"
    charge_character_downtime(
        character,
        db,
        search_result["days"],
        reason=f"Поиск {mode_label}: {item_data['item_name']}",
        source="shop",
    )

    subtract_gold_amount(
        inventory,
        search_result["hireling_cost"],
        "Недостаточно золота для наёмников"
    )

    price_roll = None
    multiplier = None
    item_price = None
    if search_result["success"]:
        if item_data["mode"] == "buy":
            price_roll, multiplier = roll_buy_price_multiplier(item_data["rarity"])
        else:
            price_roll, multiplier = roll_sell_price_multiplier(item_data["rarity"])
        item_price = max(1, round(base_price_for_item(
            item_data["rarity"],
            item_data["is_consumable"]
        ) * multiplier))

    quote = ShopQuote(
        **item_data,
        **search_result,
        price_roll=price_roll,
        multiplier=multiplier,
        item_price=item_price,
        inventory_id=inventory.id
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    db.refresh(inventory)

    return serialize_quote(quote, inventory)

@router.post("/characters/{character_id}/shop/buy", response_model=ShopResult)
def buy_shop_item(
    character_id: int,
    confirm_data: ShopConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    character = get_character_for_current_user(character_id, current_user, db)
    inventory = get_character_inventory(character_id, current_user, db)
    quote = get_quote_for_inventory(inventory, confirm_data.quote_id, db)
    if quote.mode != "buy":
        raise HTTPException(
            status_code=400,
            detail="Shop result is not a buy result"
        )

    subtract_gold_amount(inventory, quote.item_price, "Недостаточно золота")
    db.add(InventoryItem(
        name=quote.item_name,
        rarity=quote.rarity,
        is_consumable=quote.is_consumable,
        inventory_id=inventory.id
    ))
    quote.is_consumed = True
    record_shop_transaction(quote, character, inventory, current_user, db)
    db.commit()
    db.refresh(quote)
    db.refresh(inventory)

    return serialize_quote(quote, inventory)

@router.post("/characters/{character_id}/shop/sell", response_model=ShopResult)
def sell_shop_item(
    character_id: int,
    confirm_data: ShopConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    character = get_character_for_current_user(character_id, current_user, db)
    inventory = get_character_inventory(character_id, current_user, db)
    quote = get_quote_for_inventory(inventory, confirm_data.quote_id, db)
    if quote.mode != "sell":
        raise HTTPException(
            status_code=400,
            detail="Shop result is not a sell result"
        )

    item = db.query(InventoryItem).filter(
        InventoryItem.id == quote.item_id,
        InventoryItem.inventory_id == inventory.id
    ).first()

    if not item:
        raise HTTPException(
            status_code=400,
            detail="Предмета нет в инвентаре"
        )

    add_currency(inventory, gold=quote.item_price)
    db.delete(item)
    quote.is_consumed = True
    record_shop_transaction(quote, character, inventory, current_user, db)
    db.commit()
    db.refresh(quote)
    db.refresh(inventory)

    return serialize_quote(quote, inventory)
