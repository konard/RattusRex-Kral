import random

from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.calendar import GAME_EPOCH
from app.db.database import SessionLocal
from app.models.character import Character
from app.models.user import User
from app.api.users import get_current_user
from app.schemas.character import (
    AbilityRollResponse,
    CharacterCreate,
    CharacterUpdate,
    SavingThrowRollResponse,
)
from app.api.users import get_db

ABILITY_FIELDS = {
    "strength": "Сила",
    "dexterity": "Ловкость",
    "constitution": "Телосложение",
    "intelligence": "Интеллект",
    "wisdom": "Мудрость",
    "charisma": "Харизма",
}


router = APIRouter()
MAX_CHARACTERS_PER_USER = 10


def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()

@router.post("/characters")
def create_character(
    character_data: CharacterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    character_count = db.query(Character).filter(
        Character.user_id == current_user.id
    ).count()
    if character_count >= MAX_CHARACTERS_PER_USER:
        raise HTTPException(
            status_code=400,
            detail="Достигнут лимит персонажей (10 из 10)."
        )

    game_created_at = character_data.game_created_at or GAME_EPOCH
    if game_created_at < GAME_EPOCH:
        raise HTTPException(
            status_code=400,
            detail=(
                "Дата создания персонажа не может быть раньше начала игры "
                f"({GAME_EPOCH.strftime('%d.%m.%Y')})."
            )
        )

    character = Character(
        name=character_data.name,
        class_name=character_data.class_name,
        game_created_at=game_created_at,
        subclass=character_data.subclass,
        race=character_data.race,
        background=character_data.background,
        strength=character_data.strength,
        dexterity=character_data.dexterity,
        constitution=character_data.constitution,
        intelligence=character_data.intelligence,
        wisdom=character_data.wisdom,
        charisma=character_data.charisma,
        investigation=character_data.investigation,
        hp=character_data.hp,
        temp_hp=character_data.temp_hp,
        armor_class=character_data.armor_class,
        speed=character_data.speed,
        level=character_data.level,
        route=character_data.route,
        user_id=current_user.id
    )

    db.add(character)

    db.commit()

    db.refresh(character)

    return {
        "id": character.id,
        "name": character.name,
        "class_name": character.class_name,
        "level": character.level,
        "xp": character.xp,
        "route": character.route,
        "game_created_at": character.game_created_at,
        "subclass": character.subclass,
        "race": character.race,
        "background": character.background,
        "strength": character.strength,
        "dexterity": character.dexterity,
        "constitution": character.constitution,
        "intelligence": character.intelligence,
        "wisdom": character.wisdom,
        "charisma": character.charisma,
        "investigation": character.investigation,
        "hp": character.hp,
        "temp_hp": character.temp_hp,
        "armor_class": character.armor_class,
        "speed": character.speed
    }

@router.get("/characters")
def get_characters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    characters = db.query(Character).filter(
        Character.user_id == current_user.id
    ).all()

    return characters


@router.get("/characters/transfer-targets")
def get_transfer_targets(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    return [{
        "id": character.id,
        "name": character.name,
        "class_name": character.class_name,
        "level": character.level,
        "owner_username": character.owner.username
    } for character in db.query(Character).all()]


@router.patch("/characters/{character_id}")
def update_character(
    character_id: int,
    character_data: CharacterUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    character = db.query(Character).filter(
        Character.id == character_id,
        Character.user_id == current_user.id
    ).first()

    if not character:
        raise HTTPException(
            status_code=404,
            detail="Character not found"
        )
    update_data = character_data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(character, key, value)

    db.commit()
    db.refresh(character)

    return character


@router.post(
    "/characters/{character_id}/roll-ability/{ability}",
    response_model=AbilityRollResponse
)
def roll_ability(
    character_id: int,
    ability: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if ability not in ABILITY_FIELDS:
        raise HTTPException(status_code=400, detail="Неизвестная характеристика")

    character = db.query(Character).filter(
        Character.id == character_id,
        Character.user_id == current_user.id
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    score = getattr(character, ability)
    modifier = (score - 10) // 2
    roll = random.randint(1, 20)
    total = roll + modifier
    mod_text = f"{'+' if modifier >= 0 else ''}{modifier}"
    ability_label = ABILITY_FIELDS[ability]

    from app.api.chat import create_roll_chat_message
    create_roll_chat_message(
        db=db,
        user=current_user,
        formula=f"1d20{mod_text}",
        rolls=[roll],
        total=total,
        content=(
            f"{current_user.username}: {character.name} — бросок {ability_label}. "
            f"Бросок: {roll}. Модификатор: {mod_text}. Итог: {total}."
        )
    )
    db.commit()

    return {
        "ability": ability,
        "score": score,
        "modifier": modifier,
        "roll": roll,
        "total": total,
    }


@router.post(
    "/characters/{character_id}/roll-saving-throw/{ability}",
    response_model=SavingThrowRollResponse
)
def roll_saving_throw(
    character_id: int,
    ability: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if ability not in ABILITY_FIELDS:
        raise HTTPException(status_code=400, detail="Неизвестная характеристика")

    character = db.query(Character).filter(
        Character.id == character_id,
        Character.user_id == current_user.id
    ).first()
    if not character:
        raise HTTPException(status_code=404, detail="Персонаж не найден")

    score = getattr(character, ability)
    bonus = (score - 10) // 2
    roll = random.randint(1, 20)
    total = roll + bonus
    bonus_text = f"{'+' if bonus >= 0 else ''}{bonus}"
    ability_label = ABILITY_FIELDS[ability]

    from app.api.chat import create_roll_chat_message
    create_roll_chat_message(
        db=db,
        user=current_user,
        formula=f"1d20{bonus_text}",
        rolls=[roll],
        total=total,
        content=(
            f"{current_user.username}: {character.name} — спасбросок {ability_label}. "
            f"Бросок: {roll}. Бонус: {bonus_text}. Итог: {total}."
        )
    )
    db.commit()

    return {
        "ability": ability,
        "bonus": bonus,
        "roll": roll,
        "total": total,
    }
