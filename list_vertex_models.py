from google import genai
from google.oauth2 import service_account

from core.settings_manager import settings


def main():
    key_path = settings.get("gcp_key_path", "")
    project_id = settings.infer_project_id_from_key_path(key_path)
    if not key_path or not project_id:
        raise SystemExit("Set gcp_key_path terlebih dahulu di pengaturan.")

    creds = service_account.Credentials.from_service_account_file(
        key_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )

    client = genai.Client(
        vertexai=True,
        project=project_id,
        location="global",
        credentials=creds,
    )

    for model in client.models.list():
        name = getattr(model, "name", None)
        if name and "/models/" in name:
            name = name.split("/")[-1]
        print(name, getattr(model, "supported_actions", None))


if __name__ == "__main__":
    main()
