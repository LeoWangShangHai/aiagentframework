import os
from pathlib import Path
from functools import lru_cache


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required env var: {name}")
    return value.strip()


@lru_cache(maxsize=1)
def create_azure_responses_agent():
    # Load local env files (dev convenience). Priority:
    # 1) config/azure_openai.env
    # 2) .env
    try:
        from dotenv import load_dotenv  # type: ignore

        project_root = Path(__file__).resolve().parents[3]
        load_dotenv(dotenv_path=project_root / "config" / "azure_openai.env", override=True)
        load_dotenv(dotenv_path=project_root / ".env", override=True)
    except Exception:
        pass

    # Import lazily so the main FastAPI app can still start without agent deps installed.
    from agent_framework.azure import AzureOpenAIResponsesClient  # type: ignore

    endpoint = _get_required_env("AZURE_OPENAI_ENDPOINT")
    deployment_name = _get_required_env("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION")
    tenant_id = os.getenv("AZURE_TENANT_ID", "").strip()
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()

    kwargs: dict = {
        "endpoint": endpoint,
        "deployment_name": deployment_name,
    }
    if api_version:
        kwargs["api_version"] = api_version

    if api_key:
        # Key auth
        # Keep AZURE_OPENAI_API_KEY as-is, and avoid inheriting other OpenAI key env vars.
        os.environ.pop("OPENAI_API_KEY", None)
        kwargs["api_key"] = api_key
    else:
        # Entra ID auth via Azure Identity (recommended for local dev + production).
        # Some SDK layers auto-detect API keys from env vars even if a credential is supplied.
        # Since we're using Entra ID in this branch, explicitly remove them.
        os.environ.pop("AZURE_OPENAI_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)

        # NOTE: Some Azure OpenAI resources disable key auth; this avoids that issue.
        try:
            from azure.identity import DefaultAzureCredential  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "Entra ID auth requires azure-identity. Install with: "
                "py -m pip install -r backend\\requirements-agent.txt"
            ) from exc

        if tenant_id:
            # Prefer Azure CLI token from the specified tenant (prevents tenant mismatch).
            from azure.identity import AzureCliCredential  # type: ignore

            kwargs["credential"] = AzureCliCredential(tenant_id=tenant_id)
        else:
            kwargs["credential"] = DefaultAzureCredential(exclude_interactive_browser_credential=False)

    client = AzureOpenAIResponsesClient(**kwargs)

    return client.create_agent(
        name=os.getenv("AGENT_NAME", "Assistant"),
        instructions=os.getenv(
            "AGENT_INSTRUCTIONS",
            "You are a helpful assistant.",
        ),
    )
