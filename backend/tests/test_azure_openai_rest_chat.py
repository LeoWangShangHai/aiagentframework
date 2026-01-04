from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest


def _format_url(url: str, params: dict | None) -> str:
    if not params:
        return url
    # Keep it simple and stable for logs (only api-version is expected).
    if "api-version" in params and params["api-version"]:
        return f"{url}?api-version={params['api-version']}"
    return url


def _load_env_file_if_present() -> None:
    """Load config/azure_openai.env into os.environ without extra deps.

    - Does not override existing env vars.
    - Supports simple KEY=VALUE lines and ignores comments.
    """

    project_root = Path(__file__).resolve().parents[2]
    env_path = project_root / "config" / "azure_openai.env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        if not key:
            continue

        os.environ.setdefault(key, value)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _extract_choice_text(data: dict) -> str:
    """Extract assistant text from a Chat Completions response."""

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AssertionError(f"Unexpected response shape: {data}")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise AssertionError(f"Unexpected response shape: {data}")

    content = message.get("content")

    # Typical chat/completions shape: content is a string
    if isinstance(content, str):
        return content

    # Some APIs can return structured content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    return str(content)


def _extract_responses_text(data: dict) -> str:
    """Extract assistant text from a Responses API payload."""

    # Common convenience field
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    # OpenAI Responses API shape: output -> [{type: 'message', content: [{type:'output_text', text:'...'}]}]
    output = data.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        text = c.get("text")
                        if isinstance(text, str) and text:
                            parts.append(text)
                    elif isinstance(c, str):
                        parts.append(c)
        if parts:
            return "".join(parts)

    # Fallbacks
    for key in ("text", "content", "message"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value

    return str(data)


def _normalize_azure_host(endpoint_or_base_url: str) -> str:
    """Normalize Azure OpenAI host endpoint.

    Users sometimes paste either:
    - resource endpoint: https://<resource>.openai.azure.com/
    - base_url:         https://<resource>.openai.azure.com/openai/v1/

    This returns the host endpoint without any /openai/... suffix.
    """

    value = endpoint_or_base_url.strip().rstrip("/")
    marker = "/openai/"
    if marker in value:
        return value.split(marker, 1)[0]
    return value


def test_azure_openai_rest_chat_completions_pong():
    """Direct REST test for Azure OpenAI Responses API.

    Required env vars:
    - AZURE_OPENAI_ENDPOINT
    - AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME (used as deployment for responses)
    - AZURE_OPENAI_API_VERSION (optional; if omitted, the test will try calling without api-version)
    - AZURE_OPENAI_API_KEY (this test uses key auth)

    Notes:
    - This test does NOT use agent-framework; it calls Azure OpenAI REST API directly.
    - If your resource disables key auth, this test will fail/need token auth.
    """

    _load_env_file_if_present()

    if os.getenv("RUN_AZURE_OPENAI_REST_TESTS", "").strip() not in {"1", "true", "True"}:
        pytest.skip("Set RUN_AZURE_OPENAI_REST_TESTS=1 to enable Azure OpenAI REST integration tests")

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    deployment = os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "").strip()
    api_version = (
        os.getenv("AZURE_OPENAI_REST_API_VERSION", "").strip()
        or os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
    )
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()

    if not endpoint or not deployment:
        pytest.skip("Requires Azure OpenAI env (set config/azure_openai.env or env vars)")

    # This test intentionally uses REST + key auth only.
    if not api_key:
        pytest.skip("Requires AZURE_OPENAI_API_KEY for REST (key auth) test")

    host = _normalize_azure_host(endpoint)

    # agent-framework uses the OpenAI Python SDK Azure mode with base_url ending in /openai/v1/
    # and passes the Azure deployment name as `model`.
    url_v1 = f"{host}/openai/v1/responses"
    url_deployments = f"{host}/openai/deployments/{deployment}/responses"

    payload = {
        "model": deployment,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "你是什么模型？"},
                ],
            }
        ],
        "max_output_tokens": 256,
    }

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    params_with_version = {"api-version": api_version} if api_version else None

    def _needs_api_version(resp: httpx.Response) -> bool:
        text = (resp.text or "").lower()
        return resp.status_code in {400, 404} and "api-version" in text and "missing" in text

    def _unsupported_api_version(resp: httpx.Response) -> bool:
        text = (resp.text or "").lower()
        return resp.status_code == 400 and "api version" in text and "not supported" in text

    # NOTE: We deliberately never print the API key.
    print("\n=== Azure OpenAI REST test (Responses) ===")
    print(f"Host: {host}")
    print(f"Deployment(model): {deployment}")
    if api_version:
        print(f"api-version (configured): {api_version}")
    print("Request JSON:")
    print(payload)

    attempts: list[tuple[str, dict | None, httpx.Response]] = []
    with httpx.Client(timeout=60.0) as client:
        # Prefer versionless calls (some environments route /openai/v1 without api-version).
        r1 = client.post(url_v1, params=None, headers=headers, json=payload)
        attempts.append((url_v1, None, r1))
        print(f"Attempt: {_format_url(url_v1, None)} -> HTTP {r1.status_code}")

        # If the service requires api-version but we don't have one configured, fail early with guidance.
        if r1.status_code != 200 and _needs_api_version(r1) and not params_with_version:
            raise AssertionError(
                "Azure OpenAI endpoint requires an api-version query param, but none is configured."
                "\nSet one of:"
                "\n- AZURE_OPENAI_REST_API_VERSION (preferred for this test)"
                "\n- AZURE_OPENAI_API_VERSION"
                "\n\nThen re-run:"
                "\n  $env:RUN_AZURE_OPENAI_REST_TESTS=\"1\"; py -m pytest -vv -s -q backend/tests/test_azure_openai_rest_chat.py"
            )

        if r1.status_code != 200 and params_with_version and _needs_api_version(r1):
            r1v = client.post(url_v1, params=params_with_version, headers=headers, json=payload)
            attempts.append((url_v1, params_with_version, r1v))
            print(f"Attempt: {_format_url(url_v1, params_with_version)} -> HTTP {r1v.status_code}")
        elif r1.status_code != 200 and params_with_version and _unsupported_api_version(r1):
            # api-version in env might be wrong; keep the versionless attempt as the fallback.
            pass

        # If v1 failed, try deployments-style as a fallback.
        if all(r.status_code != 200 for (_, _, r) in attempts):
            r2 = client.post(url_deployments, params=None, headers=headers, json=payload)
            attempts.append((url_deployments, None, r2))
            print(f"Attempt: {_format_url(url_deployments, None)} -> HTTP {r2.status_code}")

            if r2.status_code != 200 and params_with_version and _needs_api_version(r2):
                r2v = client.post(url_deployments, params=params_with_version, headers=headers, json=payload)
                attempts.append((url_deployments, params_with_version, r2v))
                print(f"Attempt: {_format_url(url_deployments, params_with_version)} -> HTTP {r2v.status_code}")

    ok = next(((u, p, r) for (u, p, r) in attempts if r.status_code == 200), None)
    if ok is None:
        details = []
        for u, p, r in attempts:
            u2 = f"{u}?api-version={api_version}" if p else u
            details.append(f"- URL: {u2}\n  HTTP: {r.status_code}\n  Response: {r.text}")

        attempts_block = "\n".join(details)

        raise AssertionError(
            "Azure OpenAI REST failed"
            f"\n- Host: {host}"
            f"\n- Deployment(model): {deployment}"
            f"\n- Attempts:\n{attempts_block}"
            "\n\nCommon causes:"
            "\n- Wrong Azure OpenAI resource endpoint"
            "\n- Wrong deployment name for this resource"
            "\n- api-version required/unsupported (if you see an error about missing api-version, set AZURE_OPENAI_API_VERSION)"
            "\n- Key auth disabled for this resource"
        )

    url, _, r = ok
    print(f"Succeeded: {url} -> HTTP {r.status_code}")

    data = r.json()
    print("Response JSON:")
    print(data)

    text = _extract_responses_text(data).strip()
    print("Extracted text:")
    print(text)

    # This is an integration smoke test: ensure we got any non-empty textual output.
    assert text, f"Empty model output. Full response: {data!r}"
