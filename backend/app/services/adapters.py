from abc import ABC, abstractmethod
import json
from typing import Any

from ..config import Settings, get_settings
from ..domain import DOMAIN_MODELS
from .prompts import prompt_context_for_task
from .providers import OpenAIResponsesClient


class DirectorAdapter(ABC):
    provider_name = "unknown"
    model_name = "unknown"
    fallback_reason: str | None = None

    @abstractmethod
    def generate(self, task: str, context: dict[str, Any]) -> Any:
        raise NotImplementedError

    def build_prompt(self, task: str, context: dict[str, Any]) -> str:
        prompt_context = prompt_context_for_task(task, context)
        return (
            f"Generate the {task} asset for this confirmed directing context. "
            "Return only data that satisfies the supplied schema.\n"
            f"CONTEXT:\n{json.dumps(prompt_context, ensure_ascii=False, default=str)}"
        )

    def repair(
        self,
        task: str,
        invalid_output: Any,
        validation_errors: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> Any:
        """Retry hook for providers; demo mode deterministically regenerates."""
        return self.generate(task, context)

    def regenerate_shot(
        self,
        current_shot: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        generated = self.generate("shots", context)
        return next(
            shot
            for shot in generated["shots"]
            if shot["id"] == current_shot["id"]
        )


class DemoDirectorAdapter(DirectorAdapter):
    """Deterministic fallback used until provider credentials are configured."""

    provider_name = "demo"
    model_name = "deterministic-v1"

    def __init__(self, *, fallback_reason: str | None = None) -> None:
        self.fallback_reason = fallback_reason

    def generate(self, task: str, context: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "world": self._world,
            "character": self._character,
            "story": self._story,
            "shots": self._shots,
        }
        if task not in handlers:
            raise ValueError(f"Unsupported director task: {task}")
        return handlers[task](context)

    def _world(self, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": "潮汐之上的城",
            "era": "近未来 · 记忆工业衰退期",
            "location": "漂浮于旧海岸线之上的雨城",
            "culture": "以纸质地图保存私人记忆",
            "visual_style": "诗性复古未来主义",
            "palette": ["#17373d", "#8ca4a3", "#e4ad59", "#d8d2c2", "#071011"],
            "lighting": "大面积冷青环境光；真实记忆使用暖金点光源",
            "emotion_theme": "遗忘不是背叛，而是一种自救",
            "immutable_rules": {
                "world_rules": [
                    "记忆以纸质地图保存，禁止数字化复制",
                    "雨水会使被封存的记忆短暂显形",
                    "城市高度随集体遗忘程度变化",
                ],
                "geography": [
                    "城市漂浮于东部旧海岸线上空",
                    "下层是被海水淹没的旧城区",
                    "末班列车连接现实层与记忆层",
                ],
                "architecture": [
                    "潮湿粗粝的混凝土站台",
                    "细长悬索与复古有轨电车结构",
                    "建筑轮廓避免现代玻璃幕墙",
                ],
                "technology": [
                    "模拟机械优先于数字屏幕",
                    "发光墨水用于显示记忆路径",
                    "交通系统依赖纸质打孔票",
                ],
                "materials": ["旧纸纤维", "氧化铜", "湿润混凝土", "磨砂玻璃"],
                "cinematography": {
                    "lens_language": ["24mm 环境建立", "50mm 人物关系", "85mm 记忆特写"],
                    "composition": ["负空间突出孤独", "轨道线条引导视线"],
                    "camera_movement": ["克制慢推", "转折处短促手持", "结尾升空拉远"],
                    "lighting_rules": ["环境光仅用冷青", "真实记忆使用暖金点光"],
                },
                "visual_exclusions": [
                    "高饱和霓虹赛博朋克",
                    "洁净未来主义表面",
                    "无叙事意义的全息屏幕",
                ],
            },
            "mutable_state": {
                "weather": "持续细雨，峰值段转为短时暴雨",
                "time_of_day": "午夜至黎明前",
                "season": "潮湿初冬",
                "public_mood": "克制、警觉、等待某件事发生",
                "active_location": "潮汐城中央高架月台",
            },
            "locked_fields": [],
        }

    def _character(self, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": "CHAR-001",
            "name": "黎夏",
            "age": 27,
            "role": "记忆地图师",
            "appearance": "短黑发、灰绿色眼睛、左眉尾浅疤、墨绿防水长风衣",
            "personality": ["敏锐", "克制", "固执"],
            "background": "替城市居民修复被雨水损坏的记忆地图",
            "growth": ["寻找答案", "直面选择", "选择当下"],
            "continuity_lock": ["发型", "眉疤", "瞳色", "风衣长度"],
            "negative_constraints": [
                "禁止改变短黑发与左眉尾浅疤",
                "禁止偶像妆、夸张磨皮与欧美化五官",
                "禁止改变墨绿长风衣的长度和材质",
            ],
            "provider_bindings": {},
            "reference_images": [],
            "locked": False,
        }

    def _story(self, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": "末班记忆列车",
            "logline": "一位记忆地图师追上只在雨夜出现的末班列车，却发现自己寻找的人是被她亲手封存的一段记忆。",
            "acts": [
                {"time": "00-09", "title": "雨城召唤", "beat": "发现地图被雨水点亮"},
                {"time": "09-21", "title": "记忆逆流", "beat": "在情绪峰值前看见真相"},
                {"time": "21-30", "title": "留下此刻", "beat": "撕掉地图，选择当下"},
            ],
        }

    def _shots(self, context: dict[str, Any]) -> dict[str, Any]:
        character_version = context.get("asset_versions", {}).get(
            "character",
            {"asset_id": 1, "version": 1},
        )
        actions = [
            ("大远景", "24mm · 缓慢推进", "雨幕中的悬浮城首次显形", "孤独 / 预兆"),
            ("近景", "85mm · 手持微颤", "黎夏睁眼，瞳孔倒映列车灯", "苏醒 / 不安"),
            ("中景", "35mm · 横向跟拍", "她穿过无人月台追赶末班车", "追寻"),
            ("特写", "100mm · 静止", "掌心地图被雨水唤醒", "发现"),
            ("全景", "28mm · 环绕", "记忆列车从云层下方驶来", "震撼"),
            ("中近景", "50mm · 推近", "失踪的引路人隔窗出现", "思念 / 怀疑"),
            ("主观镜头", "32mm · 急速前移", "车门开启，记忆碎片逆流", "失控"),
            ("俯拍", "35mm · 垂直下降", "城市道路拼成她遗忘的名字", "真相"),
            ("近景", "65mm · 慢动作", "黎夏撕掉地图，选择留下", "释然"),
            ("大远景", "24mm · 拉远升空", "列车穿过黎明，城市重新落地", "重生"),
        ]
        shots = []
        for index, (size, camera, action, emotion) in enumerate(actions, start=1):
            start = (index - 1) * 3
            shots.append(
                {
                    "id": f"S{index:02d}",
                    "start": start,
                    "start_ms": start * 1000,
                    "duration": 3,
                    "size": size,
                    "camera": camera,
                    "action": action,
                    "emotion": emotion,
                    "character_ids": ["CHAR-001"],
                    "character_refs": [
                        {
                            "character_id": "CHAR-001",
                            "asset_id": int(character_version["asset_id"]),
                            "version": int(character_version["version"]),
                        }
                    ],
                    "prompt": f"Cinematic shot: {action}; {camera}; poetic retro-futurism; midnight cyan and memory amber; consistent character CHAR-001; 16:9",
                    "locked": False,
                }
            )
        return {"duration": 30, "fps": 24, "aspect_ratio": "16:9", "shots": shots}


class ProviderDirectorAdapter(DirectorAdapter):
    def __init__(
        self,
        *,
        client: OpenAIResponsesClient,
        model: str,
    ) -> None:
        self.client = client
        self.provider_name = client.provider_name
        self.model_name = model
        self.fallback_reason = None

    @property
    def instructions(self) -> str:
        return (
            "You are the Director Engine for a music-video preproduction system. "
            "Use only the confirmed segment and active upstream assets in context. "
            "Preserve all IDs and references exactly. Do not invent references to "
            "characters or assets absent from context. Return concise production-ready "
            "Chinese creative content and obey the JSON schema exactly."
        )

    def generate(self, task: str, context: dict[str, Any]) -> Any:
        return self.client.create_structured(
            model=self.model_name,
            instructions=self.instructions,
            prompt=self.build_prompt(task, context),
            schema_name=f"emotion_director_{task}",
            schema=DOMAIN_MODELS[task].model_json_schema(),
        )

    def repair(
        self,
        task: str,
        invalid_output: Any,
        validation_errors: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> Any:
        repair_prompt = (
            f"{self.build_prompt(task, context)}\n"
            "The previous output failed validation. Repair every listed error without "
            "changing valid upstream IDs or the confirmed segment.\n"
            f"VALIDATION_ERRORS:\n{json.dumps(validation_errors, ensure_ascii=False)}\n"
            f"INVALID_OUTPUT:\n{json.dumps(invalid_output, ensure_ascii=False, default=str)}"
        )
        return self.client.create_structured(
            model=self.model_name,
            instructions=self.instructions,
            prompt=repair_prompt,
            schema_name=f"emotion_director_{task}",
            schema=DOMAIN_MODELS[task].model_json_schema(),
        )

    def regenerate_shot(
        self,
        current_shot: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        prompt = (
            "Regenerate only this single shot's creative fields. Preserve its id, "
            "timing, character references, and lock state exactly. Return one ShotAsset.\n"
            f"CURRENT_SHOT:\n{json.dumps(current_shot, ensure_ascii=False)}\n"
            f"CONTEXT:\n{json.dumps(prompt_context_for_task('shots', context), ensure_ascii=False, default=str)}"
        )
        from ..domain import ShotAsset

        return self.client.create_structured(
            model=self.model_name,
            instructions=self.instructions,
            prompt=prompt,
            schema_name="emotion_director_single_shot",
            schema=ShotAsset.model_json_schema(),
        )


def get_director_adapter(settings: Settings | None = None) -> DirectorAdapter:
    resolved = settings or get_settings()
    if resolved.adapter_mode == "demo":
        return DemoDirectorAdapter()
    if resolved.adapter_mode != "provider":
        return DemoDirectorAdapter(
            fallback_reason=f"unsupported_adapter_mode:{resolved.adapter_mode}",
        )
    api_key = resolved.resolved_llm_api_key
    if not api_key:
        return DemoDirectorAdapter(fallback_reason="missing_llm_api_key")
    if resolved.llm_provider != "openai":
        return DemoDirectorAdapter(
            fallback_reason=f"unsupported_llm_provider:{resolved.llm_provider}",
        )
    return ProviderDirectorAdapter(
        client=OpenAIResponsesClient(
            api_key=api_key,
            base_url=resolved.llm_base_url,
            timeout_seconds=resolved.llm_timeout_seconds,
            http_retries=resolved.llm_http_retries,
        ),
        model=resolved.llm_model,
    )
