from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from html import escape
from typing import Any, Literal


ReferenceFraming = Literal["portrait", "half", "full"]


@dataclass(frozen=True)
class GeneratedCharacterReference:
    content: bytes
    content_type: str
    provider: str
    model: str


class CharacterImageAdapter(ABC):
    @abstractmethod
    async def generate(
        self,
        character: dict[str, Any],
        framing: ReferenceFraming,
    ) -> GeneratedCharacterReference:
        raise NotImplementedError


class DemoCharacterImageAdapter(CharacterImageAdapter):
    """Deterministic SVG references for credential-free and test mode."""

    provider = "demo-image"
    model = "deterministic-svg-v1"

    async def generate(
        self,
        character: dict[str, Any],
        framing: ReferenceFraming,
    ) -> GeneratedCharacterReference:
        dimensions = {
            "portrait": (640, 640, 190, 98),
            "half": (640, 800, 160, 82),
            "full": (640, 960, 135, 70),
        }
        width, height, body_width, head_radius = dimensions[framing]
        name = escape(str(character.get("name", "CHARACTER")))
        appearance = escape(str(character.get("appearance", ""))[:90])
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#102321"/><stop offset="1" stop-color="#071011"/></linearGradient></defs>
<rect width="100%" height="100%" fill="url(#bg)"/>
<g fill="none" stroke="#e4ad59" stroke-opacity=".22"><path d="M32 32h100M32 32v100M{width-32} 32h-100M{width-32} 32v100"/><path d="M32 {height-32}h100M32 {height-32}v-100M{width-32} {height-32}h-100M{width-32} {height-32}v-100"/></g>
<circle cx="{width/2}" cy="{height*.28}" r="{head_radius}" fill="#b79278"/>
<path d="M{width/2-head_radius} {height*.26} Q{width/2} {height*.10} {width/2+head_radius} {height*.26} L{width/2+head_radius*.72} {height*.16} Q{width/2} {height*.08} {width/2-head_radius*.82} {height*.18}Z" fill="#1a2321"/>
<path d="M{width/2-body_width} {height*.92} L{width/2-body_width*.75} {height*.45} Q{width/2} {height*.36} {width/2+body_width*.75} {height*.45} L{width/2+body_width} {height*.92}Z" fill="#263b35" stroke="#506d61"/>
<path d="M{width/2-34} {height*.28}h24M{width/2+10} {height*.28}h24" stroke="#667f72" stroke-width="5"/>
<text x="38" y="{height-76}" fill="#e4ad59" font-family="monospace" font-size="18">{name} · {framing.upper()}</text>
<text x="38" y="{height-44}" fill="#9ca9a3" font-family="sans-serif" font-size="13">{appearance}</text>
</svg>"""
        return GeneratedCharacterReference(
            content=svg.encode("utf-8"),
            content_type="image/svg+xml",
            provider=self.provider,
            model=self.model,
        )


def get_character_image_adapter() -> CharacterImageAdapter:
    return DemoCharacterImageAdapter()
