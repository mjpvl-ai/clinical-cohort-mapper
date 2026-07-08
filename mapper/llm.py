import os
import urllib.request
import json
import logging

logger = logging.getLogger(__name__)

def load_dotenv():
    """Load environment variables from a local .env file if it exists."""
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

# Load environment variables at module initialization
load_dotenv()

# Cache model instance to avoid reloading on every call
_local_llama_model = None

def get_local_model():
    """Initializes the local llama.cpp model once if the GGUF file exists."""
    global _local_llama_model
    if _local_llama_model is not None:
        return _local_llama_model

    gguf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "medgemma-4b-it-Q4_K_M.gguf")
    if os.path.exists(gguf_path):
        try:
            from llama_cpp import Llama
            logger.info(f"Loading local MedGemma GGUF model from {gguf_path}...")
            _local_llama_model = Llama(
                model_path=gguf_path,
                n_ctx=2048,
                n_threads=4,      # Set to number of CPU cores
                n_gpu_layers=-1,   # Offloads all layers to GPU if compiled with CUDA
                verbose=False
            )
            return _local_llama_model
        except Exception as e:
            logger.warning(f"Failed to load local GGUF model: {e}")
    return None

def call_ollama(prompt: str, json_mode: bool = False) -> str:
    """Helper to query Ollama (supports custom OLLAMA_HOST/OLLAMA_MODEL)."""
    import urllib.request
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    # Ensure scheme is present
    if not ollama_host.startswith(("http://", "https://")):
        ollama_url = f"http://{ollama_host}"
    else:
        ollama_url = ollama_host
        
    ping_url = ollama_url.rstrip("/")
    try:
        with urllib.request.urlopen(ping_url, timeout=1.0) as r:
            pass
    except Exception as e:
        raise RuntimeError(f"Ollama service is not running at {ping_url}: {e}")
        
    import ollama
    client = ollama.Client(host=ollama_url)
    ollama_model = os.environ.get("OLLAMA_MODEL", "qwen3.5:0.8b")
    response = client.chat(
        model=ollama_model,
        messages=[{'role': 'user', 'content': prompt}],
        format='json' if json_mode else None
    )
    return response['message']['content']

def call_llm(prompt: str, json_mode: bool = False) -> str:
    """Queries Gemini API with fallbacks, falling back to local GGUF MedGemma or Ollama."""
    # Check if we should bypass Gemini API and force local model
    force_local = os.environ.get("USE_LOCAL_LLM", "").lower() in ("true", "1")
    
    if force_local:
        local_model = get_local_model()
        if local_model:
            try:
                logger.info("Using local MedGemma GGUF model (forced)...")
                response = local_model(
                    prompt,
                    max_tokens=512,
                    temperature=0.1,
                    response_format={"type": "json_object"} if json_mode else None
                )
                return response["choices"][0]["text"]
            except Exception as e:
                logger.warning(f"Local MedGemma call failed: {e}")
        try:
            return call_ollama(prompt, json_mode)
        except Exception as e:
            logger.error(f"Fallback to local qwen3:0.6b failed: {e}")
            raise e

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        import time
        import urllib.error
        
        # We try only the primary model. If it hits 429/503 or fails, we immediately 
        # fall back to local models instead of spending minutes retrying.
        model = "gemini-3.1-flash-lite"
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ]
            }
            if json_mode:
                payload["generationConfig"] = {
                    "responseMimeType": "application/json"
                }
                
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                
            content = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return content
        except Exception as e:
            logger.warning(f"Gemini API call failed ({e}). Falling back immediately to local options.")
                    
    # Fallback 1: Local MedGemma GGUF (Second priority)
    local_model = get_local_model()
    if local_model:
        try:
            logger.info("Using local MedGemma GGUF model...")
            response = local_model(
                prompt,
                max_tokens=512,
                temperature=0.1,
                response_format={"type": "json_object"} if json_mode else None
            )
            return response["choices"][0]["text"]
        except Exception as e:
            logger.warning(f"Local MedGemma call failed: {e}")

    # Fallback 2: Local qwen3:0.6b model via Ollama
    try:
        return call_ollama(prompt, json_mode)
    except Exception as e:
        logger.error(f"Fallback to local qwen3:0.6b failed: {e}")
        raise e
