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

def call_llm(prompt: str, json_mode: bool = False) -> str:
    """Queries Gemini API with fallbacks, falling back to local qwen3:0.6b if needed."""
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
                    
    # Fallback to local qwen3:0.6b model via Ollama
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
