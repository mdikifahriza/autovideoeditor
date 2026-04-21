"""
Settings manager for API credentials and application preferences.

Sensitive values are stored in the OS keyring when possible.
Non-sensitive values are stored in a JSON file under LocalAppData.
"""

import json
import os

import keyring

APP_NAME = "AutoVideoEditor"
SETTINGS_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    APP_NAME,
)
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

_KEYRING_SERVICE = "AutoVideoEditor-APIKeys"
_SECURE_KEYS = ["gemini_api_key", "pexels_api_key", "pixabay_api_key"]
_GLOBAL_STABLE_GEMINI_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-pro-preview",
]
_RECOMMENDED_JSON_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]
_TASK_MODEL_HINTS = {
    "transcribe": ["native-audio", "flash-lite", "flash", "pro"],
    "planner": ["pro", "flash"],
    "vision": ["flash", "pro"],
}

_MODEL_PRESETS = {
    "fast": {
        "transcribe": "gemini-2.5-flash",
        "planner": "gemini-2.5-flash",
        "vision": "gemini-2.5-flash-lite",
    },
    "balanced": {
        "transcribe": "gemini-2.5-flash",
        "planner": "gemini-2.5-pro",
        "vision": "gemini-2.5-flash",
    },
    "accurate": {
        "transcribe": "gemini-3.1-flash-lite-preview",
        "planner": "gemini-3.1-pro-preview",
        "vision": "gemini-3-flash-preview",
    },
}

_DEFAULTS = {
    "project_mode": "voiceover",
    "review_profile": "standard",
    "ai_provider": "vertex_ai",
    "model_profile": "balanced",
    "allow_preview_models": False,
    "gemini_model_text": "gemini-2.5-flash",
    "gemini_model_transcribe": "gemini-2.5-flash",
    "gemini_model_planner": "gemini-2.5-pro",
    "gemini_model_vision": "gemini-2.5-flash",
    "gemini_model_tts": "gemini-3.1-flash-tts-preview",
    "tts_voice_name": "Kore",
    "tts_provider": "gemini",
    "gcp_project_id": "",
    "gcp_location": "global",
    "gcp_key_path": "",
    "whisper_model": "base",
    "whisper_lang": "id",
    "seg_min": 4,
    "seg_max": 12,
    "seg_ideal": 6,
    "broll_candidates": 5,
    "output_width": 1920,
    "output_height": 1080,
    "output_fps": 30,
    "output_bitrate": "8000k",
    "output_preset": "medium",
    "processing_mode": "semi_manual",
    "subtitle_enabled": False,
    "subtitle_style": "clean",
    "intro_video_path": "",
    "outro_video_path": "",
    "projects_root": os.path.join(
        os.path.expanduser("~"),
        "Documents",
        "AutoVideoEditor Projects",
    ),
    "video_encoder_mode": "auto",
    "detected_video_encoder": "",
    "detected_video_encoder_status": "Belum dicek",
    "detected_video_encoder_checked_at": 0,
}


def _read_project_id_from_service_account(path: str) -> str:
    """Read project_id from a local service account JSON file."""
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("project_id", "")).strip()
    except Exception:
        return ""


class SettingsManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if self._loaded:
            return
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        self._data = dict(_DEFAULTS)
        self._load()
        self._loaded = True

    def _load(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            for key, value in stored.items():
                if key not in _SECURE_KEYS:
                    self._data[key] = value
        except Exception as e:
            print(f"[Settings] Failed to load settings: {e}")

    def _save(self):
        safe_data = {k: v for k, v in self._data.items() if k not in _SECURE_KEYS}
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(safe_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Settings] Failed to save settings: {e}")

    def get(self, key: str, default=None):
        if key in _SECURE_KEYS:
            try:
                value = keyring.get_password(_KEYRING_SERVICE, key)
                return value if value else default
            except Exception:
                return self._data.get(key, default)
        return self._data.get(key, default)

    def set(self, key: str, value):
        if key in _SECURE_KEYS:
            try:
                keyring.set_password(_KEYRING_SERVICE, key, str(value) if value else "")
            except Exception as e:
                print(f"[Settings] Keyring error for '{key}': {e}")
                self._data[key] = value
        else:
            self._data[key] = value

        self._save()

        if key in {
            "ai_provider",
            "gemini_api_key",
            "gcp_project_id",
            "gcp_location",
            "gcp_key_path",
            "model_profile",
            "gemini_model_text",
            "gemini_model_transcribe",
            "gemini_model_planner",
            "gemini_model_vision",
        }:
            try:
                from core.ai_handler import AIHandler

                AIHandler._client = None
                AIHandler._current_provider = None
                AIHandler._current_config = None
            except Exception:
                pass

    def set_many(self, updates: dict):
        for key, value in updates.items():
            self.set(key, value)

    def infer_project_id_from_key_path(self, key_path: str = None) -> str:
        """Prefer project_id from the JSON credential file."""
        inferred = _read_project_id_from_service_account(
            key_path or self.get("gcp_key_path", "")
        )
        return inferred or str(self._data.get("gcp_project_id", "")).strip()

    def get_vertex_location(self) -> str:
        """Vertex region is intentionally locked to the global endpoint."""
        return "global"

    def get_global_gemini_models(self) -> list[str]:
        return list(_GLOBAL_STABLE_GEMINI_MODELS)

    def get_recommended_json_models(self) -> list[str]:
        return list(_RECOMMENDED_JSON_MODELS)

    def get_task_model_hints(self, task: str) -> list[str]:
        return list(_TASK_MODEL_HINTS.get(task, []))

    def get_preset_bundle(self, profile: str) -> dict:
        return dict(_MODEL_PRESETS.get(profile, _MODEL_PRESETS["balanced"]))

    def get_model_bundle(self) -> dict:
        profile = str(self.get("model_profile", "balanced") or "balanced").strip().lower()
        if profile != "manual":
            return self.get_preset_bundle(profile)
        fallback = self.get("gemini_model_text", "gemini-2.5-flash")
        return {
            "transcribe": self.get("gemini_model_transcribe", fallback),
            "planner": self.get("gemini_model_planner", fallback),
            "vision": self.get("gemini_model_vision", fallback),
        }

    def get_model_for_task(self, task: str) -> str:
        if task == "tts":
            return self.get("gemini_model_tts", "gemini-3.1-flash-tts-preview")
        bundle = self.get_model_bundle()
        return bundle.get(task, self.get("gemini_model_text", "gemini-2.5-flash"))

    def get_video_encoder_mode(self) -> str:
        mode = str(self.get("video_encoder_mode", "auto") or "auto").strip().lower()
        if mode in {"auto", "h264_qsv", "libx264"}:
            return mode
        return "auto"

    def get_video_encoder_detection(self) -> dict:
        return {
            "detected": str(self.get("detected_video_encoder", "") or "").strip(),
            "status": str(
                self.get("detected_video_encoder_status", "Belum dicek")
                or "Belum dicek"
            ).strip(),
            "checked_at": int(self.get("detected_video_encoder_checked_at", 0) or 0),
        }

    def refresh_video_encoder_detection(self, force: bool = False) -> dict:
        from core.video_encoder_manager import refresh_video_encoder_detection

        return refresh_video_encoder_detection(force=force)

    def get_effective_video_encoder(self, force_refresh: bool = False) -> dict:
        from core.video_encoder_manager import get_effective_video_encoder

        return get_effective_video_encoder(force_refresh=force_refresh)

    def validate_gemini_key(self, key: str = None) -> tuple[bool, str]:
        from google import genai
        from core.ai_response_utils import get_response_payload

        test_key = key or self.get("gemini_api_key", "")
        if not test_key:
            return False, "API key kosong"
        try:
            client = genai.Client(api_key=test_key)
            resp = client.models.generate_content(model="gemini-2.0-flash", contents="Hi")
            text, _ = get_response_payload(resp)
            if text:
                return True, "Gemini API key valid"
        except Exception as e:
            return False, f"Error: {str(e)[:80]}"
        return False, "Tidak ada respons dari Gemini"

    def validate_vertex_ai(self, project=None, location=None, key_path=None) -> tuple[bool, str]:
        """Validate Vertex AI access using the local JSON credential file."""
        from core.ai_handler import AIHandler
        from core.ai_response_utils import get_response_payload

        old_data = self._data.copy()
        success = False
        msg = "Vertex AI belum terhubung"

        try:
            if project:
                self._data["gcp_project_id"] = project
            if key_path:
                self._data["gcp_key_path"] = key_path

            inferred_project = self.infer_project_id_from_key_path(
                self._data.get("gcp_key_path", "")
            )
            if inferred_project:
                self._data["gcp_project_id"] = inferred_project

            self._data["gcp_location"] = self.get_vertex_location()
            self._data["ai_provider"] = "vertex_ai"

            client = AIHandler.get_client()
            model_name = self.get_model_for_task("planner")
            resp = client.models.generate_content(model=model_name, contents="Hi")
            text, _ = get_response_payload(resp)
            if text:
                success = True
                msg = (
                    f"Vertex AI valid | project: {self._data.get('gcp_project_id', '-')}"
                    f" | region: {self.get_vertex_location()}"
                )
        except Exception as e:
            success = False
            msg = f"Vertex error: {str(e)[:100]}"
        finally:
            self._data = old_data

        return success, msg

    def validate_pexels_key(self, key: str = None) -> tuple[bool, str]:
        import requests

        test_key = key or self.get("pexels_api_key", "")
        if not test_key:
            return False, "API key kosong"
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": test_key},
                params={"query": "nature", "per_page": 1},
                timeout=5,
            )
            if r.status_code == 200:
                return True, "Pexels API key valid"
            return False, f"Status {r.status_code}"
        except Exception as e:
            return False, f"Error: {str(e)[:80]}"

    def validate_pixabay_key(self, key: str = None) -> tuple[bool, str]:
        import requests

        test_key = key or self.get("pixabay_api_key", "")
        if not test_key:
            return False, "API key kosong"
        try:
            r = requests.get(
                "https://pixabay.com/api/videos/",
                params={"key": test_key, "q": "nature", "per_page": 3},
                timeout=5,
            )
            if r.status_code == 200:
                return True, "Pixabay API key valid"
            return False, f"Status {r.status_code}"
        except Exception as e:
            return False, f"Error: {str(e)[:80]}"


settings = SettingsManager()
