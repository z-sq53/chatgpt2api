from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:3000/ai/gpt/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate images through a local ChatGPT2API endpoint."
    )
    parser.add_argument("--prompt")
    parser.add_argument("--image", type=Path, action="append", default=[], help="Local reference image; repeat for multiple references (PNG, JPEG, WebP or GIF)")
    parser.add_argument("--check", action="store_true", help="Check authentication and models without generating an image")
    parser.add_argument("--output-dir", type=Path, default=Path.cwd() / "generated-images")
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--size")
    parser.add_argument("--quality", default="auto")
    parser.add_argument("--count", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--base-url", default=os.environ.get("CHATGPT2API_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if not args.check and not args.prompt:
        parser.error("--prompt is required unless --check is used")
    if args.check and args.image:
        parser.error("--image cannot be used with --check")
    return args


def response_error(body: bytes, status: int) -> RuntimeError:
    text = body.decode("utf-8", errors="replace")[:8192]
    try:
        payload = json.loads(text)
        detail = payload.get("detail") or payload.get("error") or payload
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("error") or detail
        text = str(detail)
    except (json.JSONDecodeError, AttributeError):
        pass
    return RuntimeError(f"ChatGPT2API returned HTTP {status}: {text}")


def request_json(url: str, api_key: str, payload: dict[str, object] | None, timeout: int) -> dict:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
    except HTTPError as exc:
        raise response_error(exc.read(), exc.code) from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach ChatGPT2API at {url}: {exc.reason}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ChatGPT2API returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("ChatGPT2API returned an unexpected response")
    return result


def image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def reference_image(path: Path) -> dict[str, str]:
    try:
        with path.open("rb") as source:
            data = source.read(50 * 1024 * 1024 + 1)
    except OSError as exc:
        raise RuntimeError(f"Cannot read reference image: {path}") from exc
    if len(data) > 50 * 1024 * 1024:
        raise RuntimeError(f"Reference image exceeds the server's 50 MB limit: {path}")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime_type = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime_type = "image/jpeg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime_type = "image/webp"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        mime_type = "image/gif"
    else:
        raise RuntimeError(f"Reference must be a non-empty PNG, JPEG, WebP or GIF image: {path}")
    return {"filename": path.name, "mime_type": mime_type, "b64_json": base64.b64encode(data).decode("ascii")}


def decode_item(item: dict, api_key: str, base_url: str, timeout: int) -> bytes:
    encoded = item.get("b64_json")
    if encoded:
        try:
            return base64.b64decode(str(encoded), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError("ChatGPT2API returned invalid base64 image data") from exc

    image_url = str(item.get("url") or "").strip()
    if not image_url:
        raise RuntimeError("ChatGPT2API response contained no b64_json or image URL")

    headers = {"Accept": "image/*"}
    image_host = urlparse(image_url).netloc
    api_host = urlparse(base_url).netloc
    if image_host and image_host == api_host:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(image_url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Image download returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot download generated image: {exc.reason}") from exc


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("CHATGPT2API_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CHATGPT2API_API_KEY is not set")

    base_url = args.base_url.rstrip("/")
    if args.check:
        result = request_json(f"{base_url}/models", api_key, None, min(args.timeout, 30))
        models = result.get("data")
        if not isinstance(models, list):
            raise RuntimeError("Model check returned an unexpected response")
        print(json.dumps({"ok": True, "models": [item.get("id") for item in models if isinstance(item, dict)]}))
        return 0
    payload: dict[str, object] = {
        "model": args.model,
        "prompt": args.prompt,
        "n": args.count,
        "quality": args.quality,
        "response_format": "b64_json",
    }
    if args.size:
        payload["size"] = args.size

    endpoint = "images/generations"
    if args.image:
        payload["images"] = [reference_image(path) for path in args.image]
        endpoint = "images/edits"

    result = request_json(
        f"{base_url}/{endpoint}", api_key, payload, args.timeout
    )
    items = result.get("data")
    if not isinstance(items, list) or not items:
        raise RuntimeError("ChatGPT2API returned no generated images")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:12]
    paths: list[str] = []
    for index, item in enumerate(items[: args.count], start=1):
        if not isinstance(item, dict):
            raise RuntimeError("ChatGPT2API returned an invalid image item")
        data = decode_item(item, api_key, base_url, args.timeout)
        if not data:
            raise RuntimeError("ChatGPT2API returned an empty image")
        path = (args.output_dir / f"chatgpt2api-{stamp}-{index}{image_extension(data)}").resolve()
        with path.open("xb") as output:
            output.write(data)
        paths.append(str(path))

    print(json.dumps({"model": args.model, "files": paths}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
