import logging
from google.genai import types
from core.ai_handler import AIHandler
from core.ai_response_utils import get_response_payload
from core.settings_manager import settings

logger = logging.getLogger(__name__)

class ResearchProvider:
    """
    Abstraksi untuk provider riset (misal: pencarian Google via Gemini Grounding).
    """

    @staticmethod
    def perform_research(query: str, log_cb=None) -> dict:
        def _log(message: str):
            if log_cb:
                log_cb(message)
            logger.info(message)

        clean_query = str(query or "").strip()
        if not clean_query:
            raise ValueError("Query riset kosong.")

        AIHandler.ensure_ready()
        client = AIHandler.get_client()
        model_name = settings.get("gemini_model_text", "gemini-2.5-flash")
        
        _log(f"Melakukan riset Google untuk: '{clean_query}'...")
        
        prompt = f"Berikan saya ringkasan informasi terbaru dan fakta-fakta penting tentang: {clean_query}. Sertakan juga sumbernya."

        try:
            # Enable Google Search as a tool for grounding
            tools = [
                types.Tool(
                    google_search=types.GoogleSearch()
                )
            ]
            config = AIHandler.prepare_config(temperature=0.3, max_tokens=4000)
            config.tools = tools
            
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            
            research_text, _ = get_response_payload(response)
            
            if not research_text:
                raise ValueError("Hasil riset kosong dari model.")
                
            _log("Riset selesai.")
            
            return {
                "query": clean_query,
                "research_text": research_text,
                "source": "google_search_grounding"
            }

        except Exception as e:
            _log(f"Riset Google gagal: {e}")
            raise RuntimeError(f"Gagal melakukan riset: {e}")

