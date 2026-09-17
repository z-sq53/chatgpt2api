---
name: chatgpt2api-image
description: Generate or edit images through the video library's local ChatGPT2API gpt-image-2 service, including product-reference image-to-image workflows, and save results locally. Use when the user asks for this Skill, 素材库 GPT 生图, ChatGPT2API or the local account pool. Supports one or more reference images. Do not use when the user asks for Codex's built-in ImageGen instead.
---

# ChatGPT2API Image

Generate or edit images with the bundled script. With `--image`, the script sends the actual reference image bytes to `/images/edits`; without references it uses `/images/generations`. Results are saved as new local files, preserving the references.

## Workflow

1. Confirm `CHATGPT2API_API_KEY` exists in the environment. It is a video-library image Key created in “AI 工具 → Codex / API 接入”. Never print the key, write it to project files, or pass it as a command-line argument. On Windows, if the current process lacks it, read the current user's persisted environment value into the child process environment without displaying it; do the same for `CHATGPT2API_BASE_URL`.
2. Choose an output directory inside the current workspace unless the user specifies another location. For image-to-image work, locate the attached or user-specified reference files and inspect them before composing the prompt. If an attachment has no accessible file path, ask the user to provide its local path or reattach it; do not silently replace the reference with a text-only description.
3. Run:

```powershell
python "C:\Users\Administrator\.codex\skills\chatgpt2api-image\scripts\generate_image.py" --prompt "<prompt>" --output-dir "<absolute-output-directory>"
```

Optional arguments:

- `--size <size>`: forward a supported size such as `1024x1024`.
- `--image <absolute-path>`: provide a product/reference image for editing; repeat this argument for multiple images in the intended order. Accepts PNG, JPEG, WebP and GIF, up to 50 MB per image. The script embeds the file bytes, so the server does not need access to the local file path.
- `--quality <quality>`: default `auto`.
- `--count <1-4>`: default `1`.
- `--base-url <url>`: overrides `CHATGPT2API_BASE_URL`, then defaults to `http://127.0.0.1:3000/ai/gpt/v1`.
- `--check`: checks `/models` without a prompt or image generation. Use after setup, a Key change, or a connection failure.
- `--model <name>`: defaults to `gpt-image-2`. Do not switch to `codex-gpt-image-2` merely because Codex is the client.

4. Read the JSON printed by the script and verify every path exists.
5. Show each generated image with an absolute Markdown image path and report the saved path.

For example, to preserve a product while changing its setting:

```powershell
python "C:\Users\Administrator\.codex\skills\chatgpt2api-image\scripts\generate_image.py" --image "D:\product\front.png" --prompt "保留参考图中产品的包装、品牌文字、颜色与比例，将背景改为浅色摄影棚台面" --output-dir "D:\product\output"
```

State which reference contains the product and which contains a style or scene when multiple references are supplied. Preserve product details according to the user's instructions, then inspect the output for visible changes; do not promise exact label or logo fidelity.

## Failure handling

- If neither process nor user environment contains a Key, direct the user to the video library's API access panel and Windows user environment settings. Keep the Key out of chat. Restart Codex after changing persistent variables.
- If the service is unreachable, check the video library at `http://127.0.0.1:3000/app/` and its Docker services; the integrated GPT service is internal and does not expose port 3001.
- A 401 means the Key expired, was disabled/revoked, or its owner is unavailable. A 403 means the endpoint is outside this Key's scope. These Keys support model listing, text-to-image generation and reference image editing; they cannot access account management or settings.
- Do not automatically resubmit image generation after a timeout: the upstream may have already generated the image. Report the uncertain outcome first.
- If the API returns an error, summarize its message without exposing request headers or secrets.
