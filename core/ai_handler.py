"""
Unified Gen AI client bootstrapper.

This module supports both Google AI Studio and Vertex AI, but the current
product direction uses Vertex AI with a local service account JSON and the
global endpoint as the default.
"""

import os
import warnings

from google import genai
from google.genai import types
from google.oauth2 import service_account

from core.settings_manager import settings

warnings.filterwarnings("ignore", category=UserWarning, module="vertexai")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="vertexai")

class VideoGenerationError(Exception):
    """Exception raised when Veo fails to generate video."""
    pass

class AIHandler:
    _client = None
    _current_provider = None
    _current_config = None

    @staticmethod
    def _get_current_config():
        provider = settings.get("ai_provider", "vertex_ai")
        key_path = settings.get("gcp_key_path", "")
        project_id = settings.infer_project_id_from_key_path(key_path)
        return {
            "provider": provider,
            "api_key": settings.get("gemini_api_key", ""),
            "project_id": project_id,
            "location": settings.get_vertex_location(),
            "key_path": key_path,
        }

    @staticmethod
    def get_client():
        provider = settings.get("ai_provider", "vertex_ai")
        current_config = AIHandler._get_current_config()

        if (
            AIHandler._client is None
            or AIHandler._current_provider != provider
            or AIHandler._current_config != current_config
        ):
            if provider == "vertex_ai":
                AIHandler._client = AIHandler._init_vertex()
            else:
                AIHandler._client = AIHandler._init_ai_studio()
            AIHandler._current_provider = provider
            AIHandler._current_config = current_config

        return AIHandler._client

    @staticmethod
    def _init_ai_studio():
        api_key = settings.get("gemini_api_key", "")
        if not api_key:
            raise ValueError("Gemini API key belum diisi di Pengaturan.")
        return genai.Client(api_key=api_key)

    @staticmethod
    def _init_vertex():
        key_path = settings.get("gcp_key_path", "")
        project_id = settings.infer_project_id_from_key_path(key_path)
        location = settings.get_vertex_location()

        if not key_path:
            raise ValueError("File Service Account JSON belum dipilih di Pengaturan.")
        if not os.path.exists(key_path):
            raise ValueError(f"File Service Account JSON tidak ditemukan: {key_path}")
        if not project_id:
            raise ValueError("project_id tidak ditemukan di file Service Account JSON.")
        if os.path.getsize(key_path) == 0:
            raise ValueError("File Service Account JSON kosong.")

        try:
            credentials = service_account.Credentials.from_service_account_file(
                key_path,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            return genai.Client(
                vertexai=True,
                project=project_id,
                location=location,
                credentials=credentials,
            )
        except Exception as e:
            raise RuntimeError(f"Gagal inisialisasi Vertex AI Client: {e}") from e

    @staticmethod
    def ensure_ready():
        """Raise a readable error if the current provider is not configured."""
        provider = settings.get("ai_provider", "vertex_ai")
        if provider == "vertex_ai":
            key_path = settings.get("gcp_key_path", "")
            if not key_path:
                raise ValueError("Pilih file Service Account JSON di Pengaturan.")
            if not settings.infer_project_id_from_key_path(key_path):
                raise ValueError("project_id tidak ditemukan di Service Account JSON.")
        else:
            if not settings.get("gemini_api_key", ""):
                raise ValueError("Gemini API key belum diisi di Pengaturan.")

    @staticmethod
    def prepare_config(temperature=0.1, max_tokens=16000, mime_type=None, schema=None):
        return types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type=mime_type,
            response_schema=schema,
        )
