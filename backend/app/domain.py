from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


class StrictDomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
CharacterId = Annotated[str, StringConstraints(pattern=r"^CHAR-\d{3}$")]
ShotId = Annotated[str, StringConstraints(pattern=r"^S\d{2}$")]


class WorldAsset(StrictDomainModel):
    name: str = Field(min_length=1, max_length=120)
    era: str = Field(min_length=1, max_length=240)
    location: str = Field(min_length=1, max_length=300)
    culture: str = Field(min_length=1, max_length=500)
    visual_style: str = Field(min_length=1, max_length=240)
    palette: list[HexColor] = Field(min_length=3, max_length=8)
    lighting: str = Field(min_length=1, max_length=500)
    emotion_theme: str = Field(min_length=1, max_length=500)


class CharacterAsset(StrictDomainModel):
    id: CharacterId
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=0, le=120)
    role: str = Field(min_length=1, max_length=160)
    appearance: str = Field(min_length=1, max_length=800)
    personality: list[str] = Field(min_length=1, max_length=8)
    background: str = Field(min_length=1, max_length=1000)
    growth: list[str] = Field(min_length=1, max_length=8)
    continuity_lock: list[str] = Field(min_length=1, max_length=16)


class StoryAct(StrictDomainModel):
    time: Annotated[str, StringConstraints(pattern=r"^\d{2}-\d{2}$")]
    title: str = Field(min_length=1, max_length=120)
    beat: str = Field(min_length=1, max_length=500)


class StoryAsset(StrictDomainModel):
    title: str = Field(min_length=1, max_length=160)
    logline: str = Field(min_length=1, max_length=1000)
    acts: list[StoryAct] = Field(min_length=3, max_length=8)


class ShotAsset(StrictDomainModel):
    id: ShotId
    start: float = Field(ge=0)
    duration: float = Field(gt=0, le=30)
    size: str = Field(min_length=1, max_length=80)
    camera: str = Field(min_length=1, max_length=240)
    action: str = Field(min_length=1, max_length=800)
    emotion: str = Field(min_length=1, max_length=240)
    character_ids: list[CharacterId] = Field(min_length=1, max_length=8)
    prompt: str = Field(min_length=1, max_length=4000)


class ShotSetAsset(StrictDomainModel):
    duration: float = Field(gt=0, le=180)
    fps: int = Field(ge=12, le=120)
    aspect_ratio: Literal["16:9", "9:16", "1:1"]
    shots: list[ShotAsset] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def validate_timeline(self) -> "ShotSetAsset":
        ids = [shot.id for shot in self.shots]
        if len(ids) != len(set(ids)):
            raise ValueError("Shot IDs must be unique")
        total = sum(shot.duration for shot in self.shots)
        if abs(total - self.duration) > 0.001:
            raise ValueError(
                f"Shot durations total {total:g}, expected declared duration {self.duration:g}"
            )
        ordered = sorted(self.shots, key=lambda shot: shot.start)
        cursor = 0.0
        for shot in ordered:
            if abs(shot.start - cursor) > 0.001:
                raise ValueError(
                    f"Shot {shot.id} starts at {shot.start:g}, expected {cursor:g}"
                )
            cursor += shot.duration
        return self


DOMAIN_MODELS: dict[str, type[StrictDomainModel]] = {
    "world": WorldAsset,
    "character": CharacterAsset,
    "story": StoryAsset,
    "shots": ShotSetAsset,
}


def _active_character_ids(context: dict[str, Any]) -> set[str]:
    character = context.get("assets", {}).get("character")
    if not isinstance(character, dict):
        return set()
    if isinstance(character.get("characters"), list):
        return {
            item["id"]
            for item in character["characters"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
    return {character["id"]} if isinstance(character.get("id"), str) else set()


def validate_domain_asset(
    kind: str,
    payload: dict[str, Any],
    context: dict[str, Any],
) -> StrictDomainModel:
    model_type = DOMAIN_MODELS[kind]
    model = model_type.model_validate(payload)
    if isinstance(model, ShotSetAsset):
        target_duration = float(context["project"]["target_duration"])
        if abs(model.duration - target_duration) > 0.001:
            raise ValueError(
                f"ShotSet duration {model.duration:g} must equal project target {target_duration:g}"
            )
        known_characters = _active_character_ids(context)
        referenced = {
            character_id
            for shot in model.shots
            for character_id in shot.character_ids
        }
        missing = sorted(referenced - known_characters)
        if missing:
            raise ValueError(
                f"ShotSet references unknown characters: {', '.join(missing)}"
            )
    return model
