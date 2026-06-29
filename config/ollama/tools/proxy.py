import os
import json
import uuid
import time
import yaml
import logging
import re
from typing import Dict, Any, List, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse, Response
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download
import httpx

# Configure standard logging
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger("proxy")

OLLAMA_BASE = "http://localhost:11435"
CONFIG_PATH = "/root/.ollama/tools/models.yaml"
CACHE_DIR = "/root/.ollama/tools/hf_cache"
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 Days

os.makedirs(CACHE_DIR, exist_ok=True)

# Globals
config = {}
tokenizer_cache = {}

HARDCODED_FALLBACKS = {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40,
    "min_p": 0.05,
    "repeat_penalty": 1.0,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "num_predict": -1,
    "num_ctx": 2048,
    "stop": None
}

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load models.yaml: {e}")
    return {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global config
    config = load_config()
    # Create httpx client with generous timeouts
    app.state.client = httpx.AsyncClient(timeout=600.0)
    yield
    await app.state.client.aclose()

app = FastAPI(lifespan=lifespan)

# --- Config & Metadata Resolution ---

def get_model_config(model_name: str) -> dict:
    model_lower = model_name.lower()
    matches = [k for k in config.get("models", {}) if k.lower() in model_lower]
    if not matches:
        return {}
    matched_key = max(matches, key=len)
    logger.debug(f"[MODEL CONFIG] Matched model '{model_name}' to key '{matched_key}'")
    return config["models"][matched_key]

def get_hf_repo_from_ollama_name(model_name: str) -> str:
    if "hf.co/" in model_name:
        return model_name.split("hf.co/")[-1].split(":")[0]
    if "huggingface.co/" in model_name:
        return model_name.split("huggingface.co/")[-1].split(":")[0]
    return model_name

def resolve_base_model(hf_repo: str) -> str:
    if "/" not in hf_repo:
        return hf_repo
    try:
        readme_path = hf_hub_download(repo_id=hf_repo, filename="README.md")
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'^base_model:[ \t]*([^\s\r\n]+)', content, re.MULTILINE)
        if match:
            base_model = match.group(1).strip('"\' ')
            logger.info(f"Resolved base model '{base_model}' from README for {hf_repo}")
            return base_model
        list_match = re.search(r'^base_model:[ \t]*\r?\n[ \t]*-[ \t]*([^\s\r\n]+)', content, re.MULTILINE)
        if list_match:
            base_model = list_match.group(1).strip('"\' ')
            logger.info(f"Resolved base model '{base_model}' from README list for {hf_repo}")
            return base_model
    except Exception as e:
        logger.debug(f"Could not resolve base model from README: {e}")
    return hf_repo

def resolve_tokenizer_repo(model_name: str, model_cfg: dict) -> str:
    # 1. Check if tokenizer_repo is explicitly defined in models.yaml
    tokenizer_repo = model_cfg.get("tokenizer_repo")
    if tokenizer_repo:
        logger.debug(f"Using explicitly defined tokenizer_repo: {tokenizer_repo}")
        return tokenizer_repo

    # 2. Otherwise resolve hf_repo
    hf_repo = model_cfg.get("hf_repo")
    if not hf_repo:
        hf_repo = get_hf_repo_from_ollama_name(model_name)
    if not hf_repo or "/" not in hf_repo:
        return hf_repo
        
    quirks = model_cfg.get("quirks", {})
    if quirks.get("skip_base_resolution"):
        logger.debug(f"Skipping base model resolution for {hf_repo} due to skip_base_resolution quirk.")
        return hf_repo
        
    return resolve_base_model(hf_repo)

def sync_model_metadata(hf_repo: str, force_refresh: bool = False) -> dict:
    if not hf_repo or "/" not in hf_repo:
        return {}
        
    safe_name = hf_repo.replace("/", "--")
    cache_path = os.path.join(CACHE_DIR, f"{safe_name}_meta.json")
    
    if os.path.exists(cache_path) and not force_refresh:
        if (time.time() - os.path.getmtime(cache_path)) < CACHE_TTL_SECONDS:
            with open(cache_path, 'r') as f:
                return json.load(f)

    logger.info(f"Syncing generation configs for repository: {hf_repo}")
    extracted = {}
    try:
        try:
            gen_path = hf_hub_download(repo_id=hf_repo, filename="generation_config.json")
            with open(gen_path, 'r') as f:
                hf_params = json.load(f)
            extracted["temperature"] = hf_params.get("temperature")
            extracted["top_p"] = hf_params.get("top_p")
            extracted["top_k"] = hf_params.get("top_k")
            extracted["min_p"] = hf_params.get("min_p")
            extracted["repeat_penalty"] = hf_params.get("repetition_penalty")
            extracted["presence_penalty"] = hf_params.get("presence_penalty")
            extracted["frequency_penalty"] = hf_params.get("frequency_penalty")
            extracted["num_predict"] = hf_params.get("max_length") or hf_params.get("max_new_tokens")
            extracted["stop"] = hf_params.get("stop_strings")
        except Exception:
            pass
            
        try:
            config_path = hf_hub_download(repo_id=hf_repo, filename="config.json")
            with open(config_path, 'r') as f:
                model_config = json.load(f)
            num_ctx_val = (
                model_config.get("max_position_embeddings") or 
                model_config.get("model_max_length") or 
                model_config.get("seq_length") or 
                model_config.get("max_seq_len")
            )
            if num_ctx_val is not None:
                extracted["num_ctx"] = int(num_ctx_val)
        except Exception:
            pass
            
        with open(cache_path, 'w') as f:
            json.dump(extracted, f)
            
    except Exception as e:
        logger.warning(f"Metadata sync skipped: {e}")
        
    return extracted

def get_tokenizer(hf_repo: str) -> AutoTokenizer:
    if hf_repo not in tokenizer_cache:
        logger.debug(f"Loading tokenizer: {hf_repo}")
        try:
            tokenizer_cache[hf_repo] = AutoTokenizer.from_pretrained(hf_repo, local_files_only=True)
        except Exception:
            tokenizer_cache[hf_repo] = AutoTokenizer.from_pretrained(hf_repo)
    return tokenizer_cache[hf_repo]

def merge_options(body: dict, model_cfg: dict, hf_defaults: dict) -> dict:
    options = body.get("options", {}) or {}
    model_defaults = model_cfg.get("defaults", {}) or {}
    
    mapped_client = {}
    if "temperature" in body and body["temperature"] is not None:
        mapped_client["temperature"] = body["temperature"]
    if "top_p" in body and body["top_p"] is not None:
        mapped_client["top_p"] = body["top_p"]
    if "presence_penalty" in body and body["presence_penalty"] is not None:
        mapped_client["presence_penalty"] = body["presence_penalty"]
    if "frequency_penalty" in body and body["frequency_penalty"] is not None:
        mapped_client["frequency_penalty"] = body["frequency_penalty"]
    if "max_tokens" in body and body["max_tokens"] is not None:
        mapped_client["num_predict"] = body["max_tokens"]
    if "stop" in body and body["stop"] is not None:
        stop_val = body["stop"]
        if isinstance(stop_val, str):
            mapped_client["stop"] = [stop_val]
        elif isinstance(stop_val, list):
            mapped_client["stop"] = stop_val
            
    client_options = {**mapped_client, **options}
    merged = {}
    for name, fallback_val in HARDCODED_FALLBACKS.items():
        if name in client_options and client_options[name] is not None:
            merged[name] = client_options[name]
        elif name in model_defaults and model_defaults[name] is not None:
            merged[name] = model_defaults[name]
        elif name in hf_defaults and hf_defaults[name] is not None:
            merged[name] = hf_defaults[name]
        elif fallback_val is not None:
            merged[name] = fallback_val
    return merged

# --- Prompt & Quirks Helpers ---

def resolve_system_prompt(system_prompt: str) -> str:
    if not system_prompt:
        return ""
    if system_prompt.endswith(".txt") or system_prompt.endswith(".md"):
        potential_path = system_prompt
        if not os.path.isabs(potential_path):
            potential_path = os.path.join("/root/.ollama/tools", potential_path)
        if os.path.exists(potential_path):
            try:
                with open(potential_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to read system prompt file {potential_path}: {e}")
    return system_prompt

def inject_system_prompt(messages: list, model_cfg: dict) -> list:
    system_prompt_raw = model_cfg.get("system_prompt")
    if not system_prompt_raw:
        return messages
    if not messages or messages[0].get("role") != "system":
        resolved = resolve_system_prompt(system_prompt_raw)
        if resolved:
            return [{"role": "system", "content": resolved}] + messages
    return messages

def build_raw_prompt(messages: list, tokenizer_repo: str, model_cfg: dict, tools: list = None) -> str:
    if not tokenizer_repo:
        raise ValueError("No tokenizer repo resolved")
    tok = get_tokenizer(tokenizer_repo)
    
    # Check if a custom chat template is specified in config
    custom_template = model_cfg.get("chat_template")
    if custom_template:
        resolved_template = resolve_system_prompt(custom_template)
        if resolved_template:
            tok.chat_template = resolved_template
            
    kwargs = {}
    if tools:
        kwargs["tools"] = tools
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **kwargs)
    logger.debug(f"[TEMPLATE OUTPUT]\n{prompt}")
    return prompt

def extract_reasoning(text: str) -> Tuple[str, str]:
    think_pattern = re.compile(r'<think>(.*?)</think>', re.DOTALL)
    match = think_pattern.search(text)
    if match:
        reasoning = match.group(1).strip()
        content = text.split('</think>', 1)[1].strip()
        logger.debug(f"[REASONING EXTRACTED]\n{reasoning}")
        return content, reasoning
    return text, ""

def parse_xml_tool_calls(text: str) -> Tuple[str, list]:
    tool_calls = []
    tool_call_pattern = re.compile(r'<tool_call>(.*?)</tool_call>', re.DOTALL)
    matches = tool_call_pattern.findall(text)
    for m in matches:
        try:
            parsed = json.loads(m.strip())
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": parsed.get("name"),
                    "arguments": json.dumps(parsed.get("arguments", parsed.get("parameters", {})))
                }
            })
        except Exception as e:
            logger.error(f"Failed to parse XML tool call JSON: {m}. Error: {e}")
    content = tool_call_pattern.sub("", text).strip()
    if tool_calls:
        logger.debug(f"[TOOL CALLS PARSED]\n{json.dumps(tool_calls, indent=2)}")
    return content, tool_calls

# --- Response Formatters ---

def format_openai_response(
    model: str, 
    content: str, 
    tool_calls: list = None, 
    reasoning_content: str = "", 
    finish_reason: str = "stop",
    prompt_tokens: int = 0,
    completion_tokens: int = 0
) -> dict:
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    if reasoning_content:
        message["reasoning_content"] = reasoning_content
        
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish_reason
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
    }

def format_ollama_response(
    model: str, 
    content: str, 
    tool_calls: list = None, 
    reasoning_content: str = "", 
    finish_reason: str = "stop"
) -> dict:
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    if reasoning_content:
        message["reasoning_content"] = reasoning_content
        
    return {
        "model": model,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "message": message,
        "done": True,
        "done_reason": finish_reason
    }

async def generate_buffered_openai_chunks(
    model: str, 
    content: str, 
    tool_calls: list = None, 
    reasoning_content: str = "", 
    finish_reason: str = "stop"
):
    chat_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())
    
    yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created_time, 'model': model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
    
    if reasoning_content:
        for i in range(0, len(reasoning_content), 100):
            chunk = reasoning_content[i:i+100]
            yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created_time, 'model': model, 'choices': [{'index': 0, 'delta': {'reasoning_content': chunk}, 'finish_reason': None}]})}\n\n"
            
    if content:
        for i in range(0, len(content), 100):
            chunk = content[i:i+100]
            yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created_time, 'model': model, 'choices': [{'index': 0, 'delta': {'content': chunk}, 'finish_reason': None}]})}\n\n"
            
    if tool_calls:
        formatted_tool_calls = []
        for idx, tc in enumerate(tool_calls):
            formatted_tool_calls.append({
                "index": idx,
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"]
                }
            })
        yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created_time, 'model': model, 'choices': [{'index': 0, 'delta': {'tool_calls': formatted_tool_calls}, 'finish_reason': finish_reason}]})}\n\n"
    else:
        yield f"data: {json.dumps({'id': chat_id, 'object': 'chat.completion.chunk', 'created': created_time, 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}]})}\n\n"
        
    yield "data: [DONE]\n\n"

async def generate_buffered_ollama_chunks(
    model: str, 
    content: str, 
    tool_calls: list = None, 
    reasoning_content: str = "", 
    finish_reason: str = "stop"
):
    created_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    yield json.dumps({
        "model": model, "created_at": created_time,
        "message": {"role": "assistant", "content": ""},
        "done": False
    }) + "\n"
    
    if reasoning_content:
        for i in range(0, len(reasoning_content), 100):
            chunk = reasoning_content[i:i+100]
            yield json.dumps({
                "model": model, "created_at": created_time,
                "message": {"role": "assistant", "reasoning_content": chunk},
                "done": False
            }) + "\n"
            
    if content:
        for i in range(0, len(content), 100):
            chunk = content[i:i+100]
            yield json.dumps({
                "model": model, "created_at": created_time,
                "message": {"role": "assistant", "content": chunk},
                "done": False
            }) + "\n"
            
    final_payload = {
        "model": model, "created_at": created_time,
        "done": True, "done_reason": finish_reason
    }
    if tool_calls:
        final_payload["message"] = {"role": "assistant", "content": "", "tool_calls": tool_calls}
    yield json.dumps(final_payload) + "\n"

# --- Endpoints ---

async def process_chat(request: Request, body: dict, is_openai: bool):
    client = request.app.state.client
    model_name = body.get("model", "")
    is_stream = body.get("stream", False)
    messages = body.get("messages", [])
    tools = body.get("tools", [])
    force_refresh = request.query_params.get("refresh") == "true"
    
    logger.debug(f"[INCOMING {'/v1/chat/completions' if is_openai else '/api/chat'}]\n{json.dumps(body, indent=2)}")
    
    model_cfg = get_model_config(model_name)
    quirks = model_cfg.get("quirks", {})
    tokenizer_repo = resolve_tokenizer_repo(model_name, model_cfg)
    hf_defaults = sync_model_metadata(tokenizer_repo, force_refresh)
    
    messages = inject_system_prompt(messages, model_cfg)
    logger.debug(f"[MESSAGES AFTER INJECTION]\n{json.dumps(messages, indent=2)}")
    
    use_raw = False
    rendered_prompt = None
    if tokenizer_repo:
        try:
            if not tools or quirks.get("tool_call_format") == "xml":
                rendered_prompt = build_raw_prompt(messages, tokenizer_repo, model_cfg, tools)
                use_raw = True
        except Exception as e:
            logger.warning(f"Jinja template failed for {model_name}, falling back to native /api/chat. Error: {e}")
            
    options = merge_options(body, model_cfg, hf_defaults)
    
    if use_raw:
        ollama_payload = {
            "model": model_name,
            "prompt": rendered_prompt,
            "raw": True,
            "stream": is_stream,
            "options": options
        }
        target_endpoint = f"{OLLAMA_BASE}/api/generate"
    else:
        ollama_payload = {
            "model": model_name,
            "messages": messages,
            "stream": is_stream,
            "options": options
        }
        if tools:
            ollama_payload["tools"] = tools
        target_endpoint = f"{OLLAMA_BASE}/api/chat"
        
    logger.debug(f"[SENDING TO OLLAMA]\nTarget: {target_endpoint}\n{json.dumps(ollama_payload, indent=2)}")
    
    if is_stream:
        # Buffer and process stream for quirks, otherwise stream directly
        needs_quirks_processing = use_raw and (quirks.get("has_reasoning_blocks") or quirks.get("tool_call_format") == "xml")
        
        async def stream_generator():
            full_response = ""
            async with client.stream("POST", target_endpoint, json=ollama_payload) as res:
                if needs_quirks_processing:
                    async for chunk in res.aiter_lines():
                        if not chunk: continue
                        data = json.loads(chunk)
                        if "response" in data:
                            full_response += data["response"]
                            
                    # Finished reading, process quirks
                    content = full_response
                    reasoning_content = ""
                    tool_calls = None
                    if quirks.get("has_reasoning_blocks"):
                        content, reasoning_content = extract_reasoning(content)
                    if quirks.get("tool_call_format") == "xml":
                        content, tool_calls = parse_xml_tool_calls(content)
                        
                    finish_reason = "tool_calls" if tool_calls else "stop"
                    generator = generate_buffered_openai_chunks if is_openai else generate_buffered_ollama_chunks
                    async for out_chunk in generator(model_name, content, tool_calls, reasoning_content, finish_reason):
                        yield out_chunk
                else:
                    # Stream directly without buffering
                    chat_id = f"chatcmpl-{uuid.uuid4()}"
                    created_time = int(time.time())
                    async for chunk in res.aiter_lines():
                        if not chunk: continue
                        if not is_openai:
                            yield chunk + "\n"
                            continue
                            
                        data = json.loads(chunk)
                        chunk_data = {
                            "id": chat_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": model_name,
                            "choices": [{"index": 0, "delta": {}}]
                        }
                        
                        if use_raw and "response" in data:
                            chunk_data["choices"][0]["delta"]["content"] = data["response"]
                            if data.get("done"):
                                chunk_data["choices"][0]["finish_reason"] = "stop"
                        elif "message" in data:
                            msg = data["message"]
                            if "content" in msg:
                                chunk_data["choices"][0]["delta"]["content"] = msg["content"]
                            if "tool_calls" in msg:
                                chunk_data["choices"][0]["delta"]["tool_calls"] = msg["tool_calls"]
                            if data.get("done"):
                                chunk_data["choices"][0]["finish_reason"] = "tool_calls" if "tool_calls" in msg else "stop"
                                
                        yield f"data: {json.dumps(chunk_data)}\n\n"
                    if is_openai:
                        yield "data: [DONE]\n\n"
                        
        media_type = "text/event-stream" if is_openai else "application/json"
        return StreamingResponse(stream_generator(), media_type=media_type)
        
    else:
        # Non-streaming
        res = await client.post(target_endpoint, json=ollama_payload)
        if res.status_code != 200:
            return Response(content=res.content, status_code=res.status_code)
            
        data = res.json()
        logger.debug(f"[OLLAMA RESPONSE]\n{json.dumps(data, indent=2)}")
        
        content = ""
        tool_calls = None
        if "response" in data:
            content = data["response"]
        elif "message" in data:
            content = data["message"].get("content", "")
            tool_calls = data["message"].get("tool_calls")
            
        reasoning_content = ""
        if use_raw:
            if quirks.get("has_reasoning_blocks"):
                content, reasoning_content = extract_reasoning(content)
            if quirks.get("tool_call_format") == "xml":
                content, tool_calls = parse_xml_tool_calls(content)
                
        finish_reason = "tool_calls" if tool_calls else "stop"
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        
        if is_openai:
            response_payload = format_openai_response(model_name, content, tool_calls, reasoning_content, finish_reason, prompt_tokens, completion_tokens)
        else:
            response_payload = format_ollama_response(model_name, content, tool_calls, reasoning_content, finish_reason)
            
        logger.debug(f"[RETURNING TO CLIENT]\n{json.dumps(response_payload, indent=2)}")
        return JSONResponse(content=response_payload)

@app.post("/v1/chat/completions")
async def handle_openai_chat(request: Request):
    body = await request.json()
    return await process_chat(request, body, is_openai=True)

@app.post("/api/chat")
async def handle_ollama_chat(request: Request):
    body = await request.json()
    return await process_chat(request, body, is_openai=False)

@app.post("/api/generate")
async def handle_ollama_generate(request: Request):
    client = request.app.state.client
    body = await request.json()
    model_name = body.get("model", "")
    prompt = body.get("prompt", "")
    sys_prompt = body.get("system", "")
    is_stream = body.get("stream", True)
    force_refresh = request.query_params.get("refresh") == "true"
    
    if body.get("raw", False):
        res = await client.post(f"{OLLAMA_BASE}/api/generate", json=body)
        return Response(content=res.content, status_code=res.status_code, headers=dict(res.headers))
        
    model_cfg = get_model_config(model_name)
    tokenizer_repo = resolve_tokenizer_repo(model_name, model_cfg)
    hf_defaults = sync_model_metadata(tokenizer_repo, force_refresh)
    
    messages = []
    resolved_sys = resolve_system_prompt(sys_prompt or model_cfg.get("system_prompt"))
    if resolved_sys:
        messages.append({"role": "system", "content": resolved_sys})
    messages.append({"role": "user", "content": prompt})
    
    use_raw = False
    rendered_prompt = prompt
    if tokenizer_repo:
        try:
            rendered_prompt = build_raw_prompt(messages, tokenizer_repo, model_cfg)
            use_raw = True
        except Exception as e:
            logger.warning(f"Generate template failed: {e}")
            
    options = merge_options(body, model_cfg, hf_defaults)
    
    ollama_payload = {
        "model": model_name,
        "prompt": rendered_prompt,
        "raw": use_raw,
        "stream": is_stream,
        "options": options
    }
    
    if is_stream:
        async def stream_generator():
            async with client.stream("POST", f"{OLLAMA_BASE}/api/generate", json=ollama_payload) as res:
                async for chunk in res.aiter_bytes():
                    yield chunk
        return StreamingResponse(stream_generator(), media_type="application/json")
    else:
        res = await client.post(f"{OLLAMA_BASE}/api/generate", json=ollama_payload)
        return Response(content=res.content, status_code=res.status_code, headers=dict(res.headers))

@app.post("/api/pull")
async def intercept_pull_command(request: Request):
    client = request.app.state.client
    body = await request.json()
    model_name = body.get("name", "")
    
    model_cfg = get_model_config(model_name)
    try:
        tokenizer_repo = resolve_tokenizer_repo(model_name, model_cfg)
        if tokenizer_repo and "/" in tokenizer_repo:
            logger.info(f"Pre-caching metadata/tokenizer for: {tokenizer_repo}")
            sync_model_metadata(tokenizer_repo, force_refresh=True)
            get_tokenizer(tokenizer_repo)
    except Exception as e:
        logger.warning(f"Failed to pre-cache tokenizer: {e}")
        
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    
    async def forward_pull_stream():
        async with client.stream("POST", f"{OLLAMA_BASE}/api/pull", json=body, headers=headers) as res:
            async for chunk in res.aiter_bytes():
                yield chunk
    return StreamingResponse(forward_pull_stream(), media_type="application/json")

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def catch_all_passthrough(path: str, request: Request):
    client = request.app.state.client
    method = request.method
    data = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    headers.pop("connection", None)
    
    try:
        req = client.build_request(method, f"{OLLAMA_BASE}/{path}", content=data, headers=headers, params=request.query_params)
        res = await client.send(req, stream=True)
        
        forward_headers = {}
        for k, v in res.headers.items():
            if k.lower() not in ["content-length", "connection", "transfer-encoding", "content-encoding"]:
                forward_headers[k] = v
                
        async def iterate_content():
            try:
                async for chunk in res.aiter_bytes():
                    yield chunk
            finally:
                await res.aclose()
                
        return StreamingResponse(iterate_content(), status_code=res.status_code, headers=forward_headers)
    except Exception as e:
        logger.error(f"Error in catch-all passthrough: {e}")
        return JSONResponse(status_code=502, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=11434)