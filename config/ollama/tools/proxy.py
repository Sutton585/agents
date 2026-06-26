import os
import time
import json
import logging
import re
import uuid
import requests
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download

# Configure standard logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI()

OLLAMA_BACKEND_URL = "http://localhost:11435" # Native Ollama port
CACHE_DIR = "/root/.ollama/tools/hf_cache"
MODEL_DEFAULTS_PATH = "/root/.ollama/tools/model_defaults.json"
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 Days

os.makedirs(CACHE_DIR, exist_ok=True)

def load_model_defaults() -> dict:
    """
    Loads custom per-model overrides from model_defaults.json if it exists.
    """
    if os.path.exists(MODEL_DEFAULTS_PATH):
        try:
            with open(MODEL_DEFAULTS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load model defaults from {MODEL_DEFAULTS_PATH}: {e}")
    return {}

def get_hf_repo_from_ollama_name(model_name: str) -> str:
    """
    Translates an Ollama identifier into a Hugging Face repo path.
    Example: 'hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF' -> 'bartowski/Llama-3.2-1B-Instruct-GGUF'
    """
    if "hf.co/" in model_name:
        return model_name.split("hf.co/")[-1].split(":")[0]
    if "huggingface.co/" in model_name:
        return model_name.split("huggingface.co/")[-1].split(":")[0]
    return model_name

def resolve_base_model(hf_repo: str) -> str:
    """
    Attempts to resolve the original base model repository for a GGUF repository
    by reading its README.md frontmatter. Returns hf_repo if no base model is found.
    """
    if "/" not in hf_repo:
        return hf_repo  # Not a Hugging Face repo format (e.g. standard 'llama3')
        
    try:
        readme_path = hf_hub_download(repo_id=hf_repo, filename="README.md")
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Match standard base_model frontmatter on the same line (uses [ \t] to prevent crossing newlines)
        match = re.search(r'^base_model:[ \t]*([^\s\r\n]+)', content, re.MULTILINE)
        if match:
            base_model = match.group(1).strip('"\' ')
            logger.info(f"Resolved base model '{base_model}' from README for {hf_repo}")
            return base_model
            
        # Match list-style base_model frontmatter on subsequent lines (handles \r\n and indentation)
        list_match = re.search(r'^base_model:[ \t]*\r?\n[ \t]*-[ \t]*([^\s\r\n]+)', content, re.MULTILINE)
        if list_match:
            base_model = list_match.group(1).strip('"\' ')
            logger.info(f"Resolved base model '{base_model}' from README list for {hf_repo}")
            return base_model
            
    except Exception as e:
        logger.debug(f"Could not resolve base model from README: {e}")
        
    return hf_repo

def sync_model_metadata(hf_repo: str, force_refresh: bool = False) -> dict:
    """
    Downloads and updates template definitions and parameter rules
    from the resolved Hugging Face base repository.
    """
    if "/" not in hf_repo:
        return {"base_repo": hf_repo}
    safe_name = hf_repo.replace("/", "--")
    cache_path = os.path.join(CACHE_DIR, f"{safe_name}_meta.json")
    
    if os.path.exists(cache_path) and not force_refresh:
        if (time.time() - os.path.getmtime(cache_path)) < CACHE_TTL_SECONDS:
            with open(cache_path, 'r') as f:
                data = json.load(f)
                if "base_repo" in data:
                    return data

    logger.info(f"Syncing template and parameters for repository: {hf_repo}")
    
    # Resolve the base repository (e.g. finding Qwen/Qwen2.5-Coder-7B from a GGUF repo)
    base_repo = resolve_base_model(hf_repo)
    
    try:
        # 1. Pull generation parameters
        try:
            gen_config_path = hf_hub_download(repo_id=base_repo, filename="generation_config.json")
            with open(gen_config_path, 'r') as f:
                hf_params = json.load(f)
        except Exception:
            hf_params = {}
            
        # Try to pull model config.json to get context window size (max_position_embeddings or similar)
        num_ctx_val = None
        try:
            model_config_path = hf_hub_download(repo_id=base_repo, filename="config.json")
            with open(model_config_path, 'r') as f:
                model_config = json.load(f)
            num_ctx_val = (
                model_config.get("max_position_embeddings") or 
                model_config.get("model_max_length") or 
                model_config.get("seq_length") or 
                model_config.get("max_seq_len")
            )
        except Exception:
            pass
        
        # 2. Extract configuration defaults
        extracted_defaults = {
            "base_repo": base_repo,
            "temperature": hf_params.get("temperature", 0.7),
            "top_p": hf_params.get("top_p", 0.9),
            "top_k": hf_params.get("top_k", 40),
            "min_p": hf_params.get("min_p", 0.05),
            "repeat_penalty": hf_params.get("repetition_penalty", 1.0),
            "presence_penalty": hf_params.get("presence_penalty", 0.0),
            "frequency_penalty": hf_params.get("frequency_penalty", 0.0),
            "num_predict": hf_params.get("max_length") or hf_params.get("max_new_tokens", -1),
            "stop": hf_params.get("stop_strings") or []
        }
        if num_ctx_val is not None:
            try:
                extracted_defaults["num_ctx"] = int(num_ctx_val)
            except Exception:
                pass

        # 3. Pull tokenizer config to check for system prompts
        try:
            tok_config_path = hf_hub_download(repo_id=base_repo, filename="tokenizer_config.json")
            with open(tok_config_path, 'r') as f:
                tok_config = json.load(f)
                
            system_prompt = tok_config.get("system_prompt") or tok_config.get("default_system_prompt")
            if system_prompt:
                extracted_defaults["system_prompt"] = system_prompt
        except Exception:
            pass

        # 4. Save to metadata cache
        with open(cache_path, 'w') as f:
            json.dump(extracted_defaults, f)
            
        return extracted_defaults
        
    except Exception as e:
        logger.warning(f"Metadata sync skipped: {e}. Engine will utilize baseline configuration profiles.")
        return {"base_repo": base_repo}

# 1. INTERCEPT INSTALLATION
@app.post("/api/pull")
async def intercept_pull_command(request: Request):
    """
    Intercepts the pull command to pre-cache the Hugging Face template
    and parameters before Ollama downloads the heavy model weights.
    """
    body = await request.json()
    model_name = body.get("name", "")
    
    if "hf.co" in model_name or "huggingface.co" in model_name:
        hf_repo = get_hf_repo_from_ollama_name(model_name)
        logger.info(f"Intercepted installation command for Hugging Face repository: {hf_repo}")
        
        # Pull metadata and cache the base repo
        meta = sync_model_metadata(hf_repo, force_refresh=True)
        base_repo = meta.get("base_repo", hf_repo)
        
        try:
            AutoTokenizer.from_pretrained(base_repo)
            logger.info(f"Precision Jinja configuration successfully staged from base model: {base_repo}")
        except Exception as e:
            logger.warning(f"Tokenizer caching deferred: {e}")

    def forward_stream():
        res = requests.post(f"{OLLAMA_BACKEND_URL}/api/pull", json=body, stream=True)
        for chunk in res.iter_lines():
            if chunk:
                yield chunk + b"\n"
    return StreamingResponse(forward_stream(), media_type="application/json")

# 2. INTERCEPT CHAT/INFERENCE (Interactive Chat)
@app.post("/api/chat")
async def intercept_chat_and_apply_jinja(request: Request):
    """
    Intercepts standard chat requests, applies the Hugging Face Jinja template natively,
    and forwards the raw formatted string to Ollama to bypass its internal templating.
    """
    body = await request.json()
    model_name = body.get("model", "")
    messages = body.get("messages", [])
    force_refresh = request.query_params.get("refresh") == "true"
    is_stream = body.get("stream", True)

    # Preprocess messages to translate tool calls and tool outputs to standard user/assistant text messages
    processed_messages = []
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            processed_messages.append({
                "role": "user",
                "content": f"Tool Output:\n{msg.get('content', '')}"
            })
        elif role == "assistant" and "tool_calls" in msg and msg["tool_calls"]:
            calls_str = ""
            for call in msg["tool_calls"]:
                func = call.get("function", {})
                calls_str += f"\nCalled tool '{func.get('name')}' with arguments: {func.get('arguments')}"
            content = msg.get("content") or ""
            processed_messages.append({
                "role": "assistant",
                "content": f"{content}\n{calls_str}".strip()
            })
        else:
            processed_messages.append(msg)
    messages = processed_messages

    hf_repo = get_hf_repo_from_ollama_name(model_name)
    hf_defaults = sync_model_metadata(hf_repo, force_refresh=force_refresh)
    base_repo = hf_defaults.get("base_repo", hf_repo)
    
    # Load per-model overrides from model_defaults.json (sorted by key length so specific overrides win)
    all_model_defaults = load_model_defaults()
    model_defaults = {}
    sorted_keys = sorted(all_model_defaults.keys(), key=len)
    for key in sorted_keys:
        overrides = all_model_defaults[key]
        if key.lower() == model_name.lower() or key.lower() in model_name.lower():
            model_defaults.update(overrides)
            
    # Resolve system_prompt if it contains a path to an external file
    system_prompt_val = model_defaults.get("system_prompt")
    if system_prompt_val:
        potential_path = system_prompt_val
        if not os.path.isabs(potential_path):
            potential_path = os.path.join("/root/.ollama/tools", potential_path)
        if (potential_path.endswith(".txt") or potential_path.endswith(".md")) and os.path.exists(potential_path):
            try:
                with open(potential_path, 'r', encoding='utf-8') as f:
                    model_defaults["system_prompt"] = f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to read system prompt file {potential_path}: {e}")
    
    # Resolve system prompt (hierarchy: Active App Payload -> Custom Model Defaults -> Repository Defaults)
    if messages and messages[0].get("role") != "system":
        system_prompt = model_defaults.get("system_prompt") or hf_defaults.get("system_prompt")
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

    try:
        # Convert messages to a raw string via native Jinja
        if "/" not in base_repo:
            raise ValueError(f"Not a Hugging Face repository format: {base_repo}")
        try:
            tokenizer = AutoTokenizer.from_pretrained(base_repo, local_files_only=True)
        except Exception:
            tokenizer = AutoTokenizer.from_pretrained(base_repo)
        rendered_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception as e:
        logger.info(f"Using default Ollama template processing for model: {model_name}. Reason: {e}")
        # Fallback to standard Ollama API if parsing fails or not a HF model
        body_copy = dict(body)
        if "options" not in body_copy or not isinstance(body_copy["options"], dict):
            body_copy["options"] = {}
        body_copy["options"]["num_ctx"] = body_copy["options"].get("num_ctx") or 32768
        body_copy["options"]["min_p"] = body_copy["options"].get("min_p") or 0.05

        headers_dict = dict(request.headers)
        headers_dict.pop("host", None)
        headers_dict.pop("content-length", None)
        res = requests.post(
            f"{OLLAMA_BACKEND_URL}/api/chat", 
            json=body_copy, 
            headers=headers_dict, 
            params=request.query_params,
            stream=True
        )
        return StreamingResponse(res.iter_content(chunk_size=4096), status_code=res.status_code)

    # Resolve options based on hierarchy: Active App Payload -> Custom Model Defaults -> Repository Defaults
    options = body.get("options", {})
    def get_param(name: str, default_val):
        return options.get(
            name, 
            model_defaults.get(
                name, 
                hf_defaults.get(name, default_val)
            )
        )

    # Reassemble options based on hierarchy and preserve custom client fields
    ollama_options = dict(options)
    standard_params = {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.0,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "num_predict": -1,
        "num_ctx": 32768,
        "min_p": 0.05
    }
    for param_name, default_val in standard_params.items():
        val = get_param(param_name, default_val)
        if val is not None:
            ollama_options[param_name] = val

    # Only forward stop tokens if they are explicitly provided in options, model_defaults, or hf_defaults
    stop_val = options.get("stop") or model_defaults.get("stop") or hf_defaults.get("stop")
    if stop_val is not None:
        ollama_options["stop"] = stop_val

    # Reassemble payload for /api/generate
    ollama_payload = {
        "model": model_name,
        "prompt": rendered_prompt,
        "raw": True, # Bypasses Go template conversion errors completely
        "stream": is_stream,
        "options": ollama_options
    }

    def stream_response():
        res = requests.post(f"{OLLAMA_BACKEND_URL}/api/generate", json=ollama_payload, stream=True)
        for chunk in res.iter_lines():
            if chunk:
                try:
                    data = json.loads(chunk.decode('utf-8'))
                    # Translate /api/generate schema {"response": "..."} to /api/chat schema {"message": {"role": "assistant", "content": "..."}}
                    if "response" in data:
                        data["message"] = {"role": "assistant", "content": data.pop("response")}
                    yield (json.dumps(data) + "\n").encode('utf-8')
                except Exception:
                    yield chunk + b"\n"
                    
    return StreamingResponse(stream_response(), media_type="application/json")

# 3. INTERCEPT GENERATE/INFERENCE (Single Prompt)
@app.post("/api/generate")
async def intercept_generate_and_apply_jinja(request: Request):
    """
    Intercepts single completion prompts (e.g. from 'ollama run model "prompt"'),
    formats them using the base model's tokenizer natively, and forwards raw to Ollama.
    """
    body = await request.json()
    model_name = body.get("model", "")
    prompt = body.get("prompt", "")
    system_prompt = body.get("system", "")
    is_stream = body.get("stream", True)
    force_refresh = request.query_params.get("refresh") == "true"
    
    # If the request is already raw, bypass proxy parsing
    if body.get("raw", False):
        headers_dict = dict(request.headers)
        headers_dict.pop("host", None)
        headers_dict.pop("content-length", None)
        res = requests.post(
            f"{OLLAMA_BACKEND_URL}/api/generate", 
            json=body, 
            headers=headers_dict, 
            params=request.query_params,
            stream=True
        )
        return StreamingResponse(res.iter_content(chunk_size=4096), status_code=res.status_code)

    hf_repo = get_hf_repo_from_ollama_name(model_name)
    hf_defaults = sync_model_metadata(hf_repo, force_refresh=force_refresh)
    base_repo = hf_defaults.get("base_repo", hf_repo)
    
    # Load per-model overrides from model_defaults.json (sorted by key length so specific overrides win)
    all_model_defaults = load_model_defaults()
    model_defaults = {}
    sorted_keys = sorted(all_model_defaults.keys(), key=len)
    for key in sorted_keys:
        overrides = all_model_defaults[key]
        if key.lower() == model_name.lower() or key.lower() in model_name.lower():
            model_defaults.update(overrides)
            
    # Resolve system_prompt if it contains a path to an external file
    system_prompt_val = model_defaults.get("system_prompt")
    if system_prompt_val:
        potential_path = system_prompt_val
        if not os.path.isabs(potential_path):
            potential_path = os.path.join("/root/.ollama/tools", potential_path)
        if (potential_path.endswith(".txt") or potential_path.endswith(".md")) and os.path.exists(potential_path):
            try:
                with open(potential_path, 'r', encoding='utf-8') as f:
                    model_defaults["system_prompt"] = f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to read system prompt file {potential_path}: {e}")
            
    # Resolve system prompt (hierarchy: Active App Payload -> Custom Model Defaults -> Repository Defaults)
    sys = system_prompt or model_defaults.get("system_prompt") or hf_defaults.get("system_prompt")
    
    # Build messages block
    messages = []
    if sys:
        messages.append({"role": "system", "content": sys})
    messages.append({"role": "user", "content": prompt})

    try:
        # Convert prompt using native Jinja
        if "/" not in base_repo:
            raise ValueError(f"Not a Hugging Face repository format: {base_repo}")
        try:
            tokenizer = AutoTokenizer.from_pretrained(base_repo, local_files_only=True)
        except Exception:
            tokenizer = AutoTokenizer.from_pretrained(base_repo)
        rendered_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception as e:
        logger.info(f"Using default Ollama template processing for model: {model_name}. Reason: {e}")
        # Fallback to standard Ollama API
        body_copy = dict(body)
        if "options" not in body_copy or not isinstance(body_copy["options"], dict):
            body_copy["options"] = {}
        body_copy["options"]["num_ctx"] = body_copy["options"].get("num_ctx") or 32768
        body_copy["options"]["min_p"] = body_copy["options"].get("min_p") or 0.05

        headers_dict = dict(request.headers)
        headers_dict.pop("host", None)
        headers_dict.pop("content-length", None)
        res = requests.post(
            f"{OLLAMA_BACKEND_URL}/api/generate", 
            json=body_copy, 
            headers=headers_dict, 
            params=request.query_params,
            stream=True
        )
        return StreamingResponse(res.iter_content(chunk_size=4096), status_code=res.status_code)

    # Resolve options based on hierarchy: Active App Payload -> Custom Model Defaults -> Repository Defaults
    options = body.get("options", {})
    def get_param(name: str, default_val):
        return options.get(
            name, 
            model_defaults.get(
                name, 
                hf_defaults.get(name, default_val)
            )
        )

    # Reassemble options based on hierarchy and preserve custom client fields
    ollama_options = dict(options)
    standard_params = {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.0,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "num_predict": -1,
        "num_ctx": 32768,
        "min_p": 0.05
    }
    for param_name, default_val in standard_params.items():
        val = get_param(param_name, default_val)
        if val is not None:
            ollama_options[param_name] = val

    # Only forward stop tokens if they are explicitly provided in options, model_defaults, or hf_defaults
    stop_val = options.get("stop") or model_defaults.get("stop") or hf_defaults.get("stop")
    if stop_val is not None:
        ollama_options["stop"] = stop_val

    # Reassemble payload
    ollama_payload = {
        "model": model_name,
        "prompt": rendered_prompt,
        "raw": True, # Instruct Ollama to bypass its internal templating
        "stream": is_stream,
        "options": ollama_options
    }

    def stream_response():
        res = requests.post(f"{OLLAMA_BACKEND_URL}/api/generate", json=ollama_payload, stream=True)
        for chunk in res.iter_lines():
            if chunk:
                yield chunk + b"\n"
                
    return StreamingResponse(stream_response(), media_type="application/json")

# 3.5. INTERCEPT OPENAI COMPATIBILITY ENDPOINTS (e.g. from custom provider)
@app.post("/v1/chat/completions")
async def intercept_openai_chat(request: Request):
    """
    Intercepts OpenAI-compatible chat requests, ensuring context window parameters (num_ctx)
    are respected by translating the request to Ollama's native endpoints.
    """
    body = await request.json()
    model_name = body.get("model", "")
    messages = list(body.get("messages", []))
    is_stream = body.get("stream", False)

    # Preprocess messages to translate tool calls and tool outputs to standard user/assistant text messages
    processed_messages = []
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            processed_messages.append({
                "role": "user",
                "content": f"Tool Output:\n{msg.get('content', '')}"
            })
        elif role == "assistant" and "tool_calls" in msg and msg["tool_calls"]:
            calls_str = ""
            for call in msg["tool_calls"]:
                func = call.get("function", {})
                calls_str += f"\nCalled tool '{func.get('name')}' with arguments: {func.get('arguments')}"
            content = msg.get("content") or ""
            processed_messages.append({
                "role": "assistant",
                "content": f"{content}\n{calls_str}".strip()
            })
        else:
            processed_messages.append(msg)
    messages = processed_messages

    # Load defaults
    all_model_defaults = load_model_defaults()
    model_defaults = {}
    sorted_keys = sorted(all_model_defaults.keys(), key=len)
    for key in sorted_keys:
        if key.lower() == model_name.lower() or key.lower() in model_name.lower():
            model_defaults.update(all_model_defaults[key])

    hf_repo = get_hf_repo_from_ollama_name(model_name)
    hf_defaults = sync_model_metadata(hf_repo)
    base_repo = hf_defaults.get("base_repo", hf_repo)

    # Reconstruct system prompt if needed
    if messages and messages[0].get("role") != "system":
        system_prompt = model_defaults.get("system_prompt") or hf_defaults.get("system_prompt")
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

    # Build options dictionary
    options = body.get("options", {})
    if not isinstance(options, dict):
        options = {}

    # Map OpenAI standard parameters into options
    temperature = body.get("temperature")
    top_p = body.get("top_p")
    presence_penalty = body.get("presence_penalty")
    frequency_penalty = body.get("frequency_penalty")
    max_tokens = body.get("max_tokens")
    stop = body.get("stop")

    if temperature is not None:
        options["temperature"] = temperature
    if top_p is not None:
        options["top_p"] = top_p
    if presence_penalty is not None:
        options["presence_penalty"] = presence_penalty
    if frequency_penalty is not None:
        options["frequency_penalty"] = frequency_penalty
    if max_tokens is not None:
        options["num_predict"] = max_tokens
    if stop is not None:
        if isinstance(stop, str):
            options["stop"] = [stop]
        elif isinstance(stop, list):
            options["stop"] = stop

    def get_param(name: str, default_val):
        return options.get(
            name,
            model_defaults.get(name, hf_defaults.get(name, default_val))
        )

    ollama_options = {}
    standard_params = {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.0,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "num_predict": -1,
        "num_ctx": 2048,  # Safe default baseline, overridden by model metadata or configuration overrides
        "min_p": 0.05
    }
    for param_name, default_val in standard_params.items():
        val = get_param(param_name, default_val)
        if val is not None:
            ollama_options[param_name] = val

    # Only forward stop tokens if they are explicitly provided in options, model_defaults, or hf_defaults
    stop_val = options.get("stop") or model_defaults.get("stop") or hf_defaults.get("stop")
    if stop_val is not None:
        ollama_options["stop"] = stop_val

    use_raw = True
    rendered_prompt = None
    try:
        if "/" not in base_repo:
            raise ValueError(f"Not a Hugging Face repository format: {base_repo}")
        try:
            tokenizer = AutoTokenizer.from_pretrained(base_repo, local_files_only=True)
        except Exception:
            tokenizer = AutoTokenizer.from_pretrained(base_repo)
        rendered_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception as e:
        logger.info(f"OpenAI Chat template translation skipped. Reason: {e}")
        use_raw = False

    if use_raw:
        ollama_payload = {
            "model": model_name,
            "prompt": rendered_prompt,
            "raw": True,
            "stream": is_stream,
            "options": ollama_options
        }
        target_endpoint = f"{OLLAMA_BACKEND_URL}/api/generate"
    else:
        ollama_payload = {
            "model": model_name,
            "messages": messages,
            "stream": is_stream,
            "options": ollama_options
        }
        if "tools" in body:
            ollama_payload["tools"] = body["tools"]
        target_endpoint = f"{OLLAMA_BACKEND_URL}/api/chat"

    chat_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    if is_stream:
        def openai_stream_generator():
            res = requests.post(target_endpoint, json=ollama_payload, stream=True)
            for chunk in res.iter_lines():
                if chunk:
                    try:
                        data = json.loads(chunk.decode('utf-8'))
                        content = ""
                        tool_calls = None
                        if "response" in data:
                            content = data["response"]
                        elif "message" in data:
                            content = data["message"].get("content", "")
                            tool_calls = data["message"].get("tool_calls")
                        
                        finish_reason = None
                        if data.get("done"):
                            finish_reason = "stop"

                        chunk_data = {
                            "id": chat_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": model_name,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": finish_reason
                                }
                            ]
                        }
                        if content:
                            chunk_data["choices"][0]["delta"]["content"] = content
                        if tool_calls:
                            chunk_data["choices"][0]["delta"]["tool_calls"] = tool_calls
                        yield f"data: {json.dumps(chunk_data)}\n\n".encode('utf-8')
                    except Exception as e:
                        logger.error(f"Error parsing stream chunk: {e}")
            yield b"data: [DONE]\n\n"

        return StreamingResponse(openai_stream_generator(), media_type="text/event-stream")
    else:
        res = requests.post(target_endpoint, json=ollama_payload)
        if res.status_code != 200:
            return StreamingResponse(res.iter_content(chunk_size=4096), status_code=res.status_code)

        full_text = ""
        tool_calls = None
        prompt_tokens = 0
        completion_tokens = 0
        try:
            data = res.json()
            if "response" in data:
                full_text = data["response"]
            elif "message" in data:
                full_text = data["message"].get("content", "")
                tool_calls = data["message"].get("tool_calls")
            
            prompt_tokens = data.get("prompt_eval_count", 0)
            completion_tokens = data.get("eval_count", 0)
        except Exception as e:
            logger.error(f"Error parsing single response: {e}")

        response_data = {
            "id": chat_id,
            "object": "chat.completion",
            "created": created_time,
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_text
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            }
        }
        if tool_calls:
            response_data["choices"][0]["message"]["tool_calls"] = tool_calls
        return response_data

@app.post("/v1/completions")
async def intercept_openai_completions(request: Request):
    """
    Intercepts OpenAI-compatible single completions, ensuring context window parameters (num_ctx)
    are respected by translating the request to Ollama's native endpoints.
    """
    body = await request.json()
    model_name = body.get("model", "")
    prompt = body.get("prompt", "")
    is_stream = body.get("stream", False)

    # Load defaults
    all_model_defaults = load_model_defaults()
    model_defaults = {}
    sorted_keys = sorted(all_model_defaults.keys(), key=len)
    for key in sorted_keys:
        if key.lower() == model_name.lower() or key.lower() in model_name.lower():
            model_defaults.update(all_model_defaults[key])

    hf_repo = get_hf_repo_from_ollama_name(model_name)
    hf_defaults = sync_model_metadata(hf_repo)

    # Build options dictionary
    options = body.get("options", {})
    if not isinstance(options, dict):
        options = {}

    # Map OpenAI standard parameters into options
    temperature = body.get("temperature")
    top_p = body.get("top_p")
    presence_penalty = body.get("presence_penalty")
    frequency_penalty = body.get("frequency_penalty")
    max_tokens = body.get("max_tokens")
    stop = body.get("stop")

    if temperature is not None:
        options["temperature"] = temperature
    if top_p is not None:
        options["top_p"] = top_p
    if presence_penalty is not None:
        options["presence_penalty"] = presence_penalty
    if frequency_penalty is not None:
        options["frequency_penalty"] = frequency_penalty
    if max_tokens is not None:
        options["num_predict"] = max_tokens
    if stop is not None:
        if isinstance(stop, str):
            options["stop"] = [stop]
        elif isinstance(stop, list):
            options["stop"] = stop

    def get_param(name: str, default_val):
        return options.get(
            name,
            model_defaults.get(name, hf_defaults.get(name, default_val))
        )

    ollama_options = {}
    standard_params = {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.0,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "num_predict": -1,
        "num_ctx": 2048,  # Safe default baseline, overridden by model metadata or configuration overrides
        "min_p": 0.05
    }
    for param_name, default_val in standard_params.items():
        val = get_param(param_name, default_val)
        if val is not None:
            ollama_options[param_name] = val

    # Only forward stop tokens if they are explicitly provided in options, model_defaults, or hf_defaults
    stop_val = options.get("stop") or model_defaults.get("stop") or hf_defaults.get("stop")
    if stop_val is not None:
        ollama_options["stop"] = stop_val

    ollama_payload = {
        "model": model_name,
        "prompt": prompt,
        "raw": True,
        "stream": is_stream,
        "options": ollama_options
    }

    completion_id = f"cmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    if is_stream:
        def openai_completion_stream_generator():
            res = requests.post(f"{OLLAMA_BACKEND_URL}/api/generate", json=ollama_payload, stream=True)
            for chunk in res.iter_lines():
                if chunk:
                    try:
                        data = json.loads(chunk.decode('utf-8'))
                        content = data.get("response", "")
                        finish_reason = "stop" if data.get("done") else None

                        chunk_data = {
                            "id": completion_id,
                            "object": "text_completion.chunk",
                            "created": created_time,
                            "model": model_name,
                            "choices": [
                                {
                                    "index": 0,
                                    "text": content,
                                    "finish_reason": finish_reason
                                }
                            ]
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n".encode('utf-8')
                    except Exception as e:
                        logger.error(f"Error parsing completions stream chunk: {e}")
            yield b"data: [DONE]\n\n"

        return StreamingResponse(openai_completion_stream_generator(), media_type="text/event-stream")
    else:
        res = requests.post(f"{OLLAMA_BACKEND_URL}/api/generate", json=ollama_payload)
        if res.status_code != 200:
            return StreamingResponse(res.iter_content(chunk_size=4096), status_code=res.status_code)

        full_text = ""
        prompt_tokens = 0
        completion_tokens = 0
        try:
            data = res.json()
            full_text = data.get("response", "")
            prompt_tokens = data.get("prompt_eval_count", 0)
            completion_tokens = data.get("eval_count", 0)
        except Exception as e:
            logger.error(f"Error parsing single completions response: {e}")

        response_data = {
            "id": completion_id,
            "object": "text_completion",
            "created": created_time,
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "text": full_text,
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            }
        }
        return response_data

# 4. PASS-THROUGH ALL OTHER REQUESTS
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def catch_all_passthrough(path: str, request: Request):
    """
    Catch-all endpoint for any unhandled routes, forwarding directly to the Ollama backend.
    """
    method = request.method
    data = await request.body()
    headers_dict = dict(request.headers)
    headers_dict.pop("host", None)
    headers_dict.pop("content-length", None)
    headers_dict.pop("connection", None)
    
    try:
        res = requests.request(
            method, 
            f"{OLLAMA_BACKEND_URL}/{path}", 
            data=data, 
            headers=headers_dict, 
            params=request.query_params
        )
        
        # Forward headers but filter out hop-by-hop headers
        forward_headers = {}
        for k, v in res.headers.items():
            if k.lower() not in ["content-length", "connection", "transfer-encoding", "content-encoding"]:
                forward_headers[k] = v
                
        from fastapi import Response
        return Response(content=res.content, status_code=res.status_code, headers=forward_headers)
    except Exception as e:
        logger.error(f"Error in catch-all passthrough: {e}")
        from fastapi import Response
        return Response(content=json.dumps({"error": str(e)}), status_code=502, media_type="application/json")

if __name__ == "__main__":
    import uvicorn
    # Start the proxy server
    uvicorn.run(app, host="0.0.0.0", port=11434)