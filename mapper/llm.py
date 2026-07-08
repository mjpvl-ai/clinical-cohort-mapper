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

def call_llm(prompt: str, json_mode: bool = False) -> str:
    """Queries Gemini API with fallbacks, falling back to local GGUF MedGemma or Ollama."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    
    if api_key:
        import time
        import urllib.error
        
        models = ["gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-2.0-flash-lite"]
        for model in models:
            for retry_attempt in range(3):
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
                    
                    # Use a fast timeout to fall back quickly if a model is overloaded
                    with urllib.request.urlopen(req, timeout=8) as response:
                        res_data = json.loads(response.read().decode("utf-8"))
                        
                    content = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    return content
                except urllib.error.HTTPError as he:
                    if he.code in [429, 503]:
                        wait_time = (retry_attempt + 1) * 3
                        logger.warning(f"Gemini API rate limited/overloaded ({he.code}) for {model}. Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.warning(f"Failed to query Gemini model {model} due to HTTP {he.code}: {he}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to query Gemini model {model}: {e}")
                    break
                    
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
        # Quick check if Ollama port is listening to avoid hanging
        import urllib.request
        try:
            with urllib.request.urlopen("http://localhost:11434", timeout=0.5) as r:
                pass
        except Exception:
            raise RuntimeError("Ollama service is not running locally.")
            
        import ollama
        response = ollama.chat(
            model='qwen3:0.6b',
            messages=[{'role': 'user', 'content': prompt}],
            format='json' if json_mode else None
        )
        return response['message']['content']
    except Exception as e:
        logger.error(f"Fallback to local qwen3:0.6b failed: {e}")
        raise e
