"""Small Python bridge for DockProof's Round 2 multimodal inspection contract.

Provider credentials stay on the server. The default remains offline/mock; a
live call is made only when VLM_MODE=live, a provider key exists and image input
is available. The observation is validated before it reaches evidence storage.
"""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
VERDICTS = {"pass", "fail", "uncertain"}


def _prompt(expected: dict[str, Any]) -> str:
    return f"""You are DockProof, an evidence-first receiving inspector. Compare the attached receipt photographs with the purchase-order details below. Return exactly one JSON object and no prose. Do not infer what a photograph cannot show. If evidence is occluded, missing, unreadable, or ambiguous, use uncertain. Do not fabricate counts, labels or damage evidence.

EXPECTED PURCHASE ORDER:
SKU: {expected.get('sku') or 'unknown'}
ASIN: {expected.get('asin') or 'unknown'}
Product: {expected.get('product_title') or 'unknown'}
Quantity: {expected.get('quantity') if expected.get('quantity') is not None else 'unknown'}
Cartons: {expected.get('cartons') if expected.get('cartons') is not None else 'unknown'}
Units per carton: {expected.get('units_per_carton') if expected.get('units_per_carton') is not None else 'unknown'}
Colour: {expected.get('colour') or 'unknown'}
Variant: {expected.get('variant') or 'unknown'}
Expected components: {json.dumps(expected.get('components') or [])}

Check identity, total quantity, carton count, units per carton, colour/variant, outer carton condition (crushing, water, tears, punctures), visible product condition, and expected components. Each check's verdict must be exactly one of pass, fail, or uncertain. Confidence is a number from 0 to 1. Report observed values when supported, otherwise null. Explain the visual evidence briefly. Output this shape (choose one allowed string for each enum):
{{"identity":{{"verdict":"uncertain","confidence":0.0,"observed_sku":null,"reason":""}},"quantity":{{"verdict":"uncertain","confidence":0.0,"observed_quantity":null,"reason":""}},"cartons":{{"verdict":"uncertain","confidence":0.0,"observed_cartons":null,"reason":""}},"units_per_carton":{{"verdict":"uncertain","confidence":0.0,"observed_units_per_carton":null,"reason":""}},"variant":{{"verdict":"uncertain","confidence":0.0,"observed_colour":null,"observed_variant":null,"reason":""}},"carton_damage":{{"verdict":"uncertain","confidence":0.0,"damage_type":"other","severity":"minor","reason":""}},"unit_damage":{{"verdict":"uncertain","confidence":0.0,"damage_type":"other","severity":"minor","reason":""}},"components":{{"verdict":"uncertain","confidence":0.0,"components":[],"reason":""}}}}"""


def _images(inputs: list[dict]) -> list[dict]:
    root = Path(os.environ.get("INPUT_DIR", ROOT / "data" / "input")).resolve()
    result = []
    for item in inputs:
        if item.get("kind") != "image":
            continue
        path = (root / item["ref"]).resolve()
        if root not in path.parents or not path.is_file():
            continue
        mime = {".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".png":"image/png", ".webp":"image/webp"}.get(path.suffix.lower())
        if mime:
            result.append({"mime": mime, "data": base64.b64encode(path.read_bytes()).decode("ascii")})
    if not result:
        raise ValueError("Photo references were present, but no readable receipt image was found.")
    return result


def _json_response(text: str) -> dict:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Live receiving model returned no JSON observation.")
    value = json.loads(match.group(0))
    required = ("identity", "quantity", "cartons", "units_per_carton", "variant", "carton_damage", "unit_damage", "components")
    for key in required:
        check = value.get(key)
        if not isinstance(check, dict) or check.get("verdict") not in VERDICTS:
            raise ValueError(f"Live receiving model returned an invalid {key} verdict.")
        confidence = check.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError(f"Live receiving model returned an invalid {key} confidence.")
    return value


def inspect_images(expected: dict, inputs: list[dict]) -> dict:
    mode = os.environ.get("VLM_MODE", "mock").lower()
    if mode != "live":
        raise ValueError("Photos are attached, but live vision is disabled. Set VLM_MODE=live with a provider key, or use the offline fixture mode.")
    photos = _images(inputs)
    prompt = _prompt(expected)
    provider = os.environ.get("VLM_PROVIDER", "").lower()
    gemini_key = os.environ.get("GEMINI_API_KEY")
    router_key = os.environ.get("OPENROUTER_API_KEY")
    timeout = float(os.environ.get("RECEIVING_VLM_TIMEOUT_S", "30"))
    if provider == "openrouter" or (not gemini_key and router_key):
        if not router_key:
            raise ValueError("VLM_PROVIDER=openrouter requires OPENROUTER_API_KEY.")
        content = [{"type":"text","text":prompt}]
        content.extend({"type":"image_url","image_url":{"url":f"data:{photo['mime']};base64,{photo['data']}"}} for photo in photos)
        response = httpx.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization":f"Bearer {router_key}","Content-Type":"application/json","X-Title":"DockProof Receiving Manager"}, json={"model":os.environ.get("OPENROUTER_MODEL","google/gemini-2.5-flash"),"messages":[{"role":"system","content":"You are an evidence-first receiving inspector. Return valid JSON only."},{"role":"user","content":content}],"temperature":0.1,"response_format":{"type":"json_object"}}, timeout=timeout)
        response.raise_for_status()
        body = response.json()
        text = body["choices"][0]["message"]["content"]
        model_name = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    elif gemini_key:
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        parts = [{"text":prompt}, *({"inline_data":{"mime_type":photo["mime"],"data":photo["data"]}} for photo in photos)]
        response = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}", json={"contents":[{"parts":parts}],"generationConfig":{"temperature":0.1,"responseMimeType":"application/json"}}, timeout=timeout)
        response.raise_for_status()
        body = response.json()
        text = body["candidates"][0]["content"]["parts"][0]["text"]
    else:
        raise ValueError("Live vision is selected but no GEMINI_API_KEY or OPENROUTER_API_KEY is configured.")
    observation = _json_response(text)
    observation["metadata"] = {"model_version":model_name,"latency_ms":None}
    return observation
