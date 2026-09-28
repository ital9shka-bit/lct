from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .contract import ContractError


class ProviderError(RuntimeError):
    """Raised when the external analysis provider cannot return a usable response."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    api_style: str
    reasoning_effort: str
    timeout_seconds: float
    image_max_edge: int
    image_jpeg_quality: int
    input_price_per_million: Optional[float]
    output_price_per_million: Optional[float]

    @classmethod
    def from_environment(cls) -> "ProviderConfig":
        style = os.getenv("AI_API_STYLE", "chat_completions").strip()
        if style not in {"responses", "chat_completions"}:
            raise ProviderError("AI_API_STYLE must be responses or chat_completions")
        image_max_edge = int(os.getenv("AI_IMAGE_MAX_EDGE", "1024"))
        image_jpeg_quality = int(os.getenv("AI_IMAGE_JPEG_QUALITY", "75"))
        if image_max_edge < 256:
            raise ProviderError("AI_IMAGE_MAX_EDGE must be at least 256")
        if not 40 <= image_jpeg_quality <= 95:
            raise ProviderError("AI_IMAGE_JPEG_QUALITY must be from 40 to 95")
        return cls(
            provider=os.getenv("AI_PROVIDER", "gatellm").strip(),
            base_url=os.getenv("AI_BASE_URL", "https://gatellm.ru/v1").rstrip("/"),
            api_key=os.getenv("AI_API_KEY", "").strip(),
            model=os.getenv("AI_MODEL", "openai/gpt-6-luna").strip(),
            api_style=style,
            reasoning_effort=os.getenv("AI_REASONING_EFFORT", "low").strip(),
            timeout_seconds=float(os.getenv("AI_TIMEOUT_SECONDS", "90")),
            image_max_edge=image_max_edge,
            image_jpeg_quality=image_jpeg_quality,
            input_price_per_million=_optional_float("AI_INPUT_PRICE_PER_MILLION"),
            output_price_per_million=_optional_float("AI_OUTPUT_PRICE_PER_MILLION"),
        )

    @property
    def endpoint(self) -> str:
        suffix = "/responses" if self.api_style == "responses" else "/chat/completions"
        return f"{self.base_url}{suffix}"


def _optional_float(name: str) -> Optional[float]:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else None


def _image_data_url(image: Mapping[str, Any], config: ProviderConfig) -> str:
    try:
        from PIL import Image, ImageOps
    except (ImportError, OSError) as exc:
        raise ProviderError(
            "Image preprocessing requires Pillow from backend/requirements-w0.txt"
        ) from exc

    raw_content = image.get("content")
    content = (
        bytes(raw_content)
        if isinstance(raw_content, (bytes, bytearray))
        else Path(image["absolute_path"]).read_bytes()
    )
    try:
        with Image.open(BytesIO(content)) as source:
            prepared = ImageOps.exif_transpose(source).convert("RGB")
            prepared.thumbnail(
                (config.image_max_edge, config.image_max_edge),
                Image.Resampling.LANCZOS,
            )
            output = BytesIO()
            prepared.save(
                output,
                format="JPEG",
                quality=config.image_jpeg_quality,
                optimize=True,
            )
    except (OSError, ValueError) as exc:
        raise ProviderError(f"Cannot preprocess image {image['image_id']}: {exc}") from exc
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _public_context(context: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "contract_version": context["contract_version"],
        "prompt_version": context["prompt_version"],
        "catalog_version": context["catalog_version"],
        "object": context["object"],
        "cameras": context["cameras"],
        "plan_items": context["plan_items"],
        "images": [
            {
                "image_id": image["image_id"],
                "camera_id": image["camera_id"],
                "sha256": image["sha256"],
            }
            for image in context["images"]
        ],
    }


def build_request_payload(
    config: ProviderConfig,
    context: Mapping[str, Any],
    schema: Mapping[str, Any],
    prompt: str,
) -> Dict[str, Any]:
    content = [
        {
            "type": "input_text" if config.api_style == "responses" else "text",
            "text": "Контекст проверки:\n"
            + json.dumps(_public_context(context), ensure_ascii=False, separators=(",", ":")),
        }
    ]
    for image in context["images"]:
        content.append(
            {
                "type": "input_text" if config.api_style == "responses" else "text",
                "text": f"Следующее изображение: image_id={image['image_id']}, camera_id={image['camera_id']}",
            }
        )
        if config.api_style == "responses":
            content.append(
                {
                    "type": "input_image",
                    "detail": "high",
                    "image_url": _image_data_url(image, config),
                }
            )
        else:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"detail": "high", "url": _image_data_url(image, config)},
                }
            )

    if config.api_style == "responses":
        return {
            "model": config.model,
            "instructions": prompt,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "stroykontrol_analysis",
                    "strict": True,
                    "schema": schema,
                }
            },
            "max_output_tokens": 6000,
            "store": False,
            **({"reasoning": {"effort": config.reasoning_effort}} if config.reasoning_effort else {}),
        }
    return {
        "model": config.model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "stroykontrol_analysis",
                "strict": True,
                "schema": schema,
            },
        },
        "max_completion_tokens": 6000,
        **({"reasoning_effort": config.reasoning_effort} if config.reasoning_effort else {}),
    }


def call_provider(
    config: ProviderConfig, payload: Mapping[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, str], int]:
    if not config.api_key:
        raise ProviderError("AI_API_KEY is empty; live W0 run was not attempted")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        config.endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            response_body = response.read()
            response_headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:4000]
        raise ProviderError(f"Provider returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProviderError(f"Provider request failed: {exc}") from exc
    duration_ms = round((time.monotonic() - started) * 1000)
    try:
        raw = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ProviderError("Provider returned non-JSON response") from exc
    if not isinstance(raw, dict):
        raise ProviderError("Provider returned a non-object JSON response")
    return raw, response_headers, duration_ms


def _response_text(raw: Mapping[str, Any], api_style: str) -> str:
    if api_style == "chat_completions":
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Chat Completions response has no message content") from exc
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [block.get("text", "") for block in content if isinstance(block, dict)]
            return "".join(texts)
        raise ProviderError("Chat Completions message content has unsupported shape")

    if isinstance(raw.get("output_text"), str):
        return raw["output_text"]
    texts = []
    for output in raw.get("output", []):
        if not isinstance(output, dict) or output.get("type") != "message":
            continue
        for block in output.get("content", []):
            if isinstance(block, dict) and block.get("type") == "output_text":
                texts.append(block.get("text", ""))
            if isinstance(block, dict) and block.get("type") == "refusal":
                raise ProviderError(f"Model refused the request: {block.get('refusal', '')}")
    if not texts:
        raise ProviderError("Responses API response has no output_text")
    return "".join(texts)


def extract_normalized_response(raw: Mapping[str, Any], api_style: str) -> Dict[str, Any]:
    text = _response_text(raw, api_style).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
            if text.lstrip().startswith("json"):
                text = text.lstrip()[4:].lstrip("\n")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractError(f"Model output is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("Model output must be a JSON object")
    return value


def usage_metrics(
    raw: Mapping[str, Any], config: ProviderConfig, duration_ms: int, request_id: str
) -> Dict[str, Any]:
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = input_tokens + output_tokens

    provider_cost = usage.get("cost", usage.get("total_cost"))
    estimated_cost = None
    cost_source = None
    if isinstance(provider_cost, (int, float)):
        estimated_cost = float(provider_cost)
        cost_source = "provider_response"
    elif (
        isinstance(input_tokens, int)
        and isinstance(output_tokens, int)
        and config.input_price_per_million is not None
        and config.output_price_per_million is not None
    ):
        estimated_cost = (
            input_tokens * config.input_price_per_million
            + output_tokens * config.output_price_per_million
        ) / 1_000_000
        cost_source = "configured_token_prices"

    return {
        "provider": config.provider,
        "model": config.model,
        "api_style": config.api_style,
        "request_id": request_id,
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": estimated_cost,
        "cost_currency": "USD" if estimated_cost is not None else None,
        "cost_source": cost_source,
    }
