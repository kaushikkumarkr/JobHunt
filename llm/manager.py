import logging
import time
import os
import requests
from typing import Optional, List, Dict
from config.loader import get_config

logger = logging.getLogger(__name__)

class CircuitBreaker:
    def __init__(self, cooldown_seconds=300):
        self.cooldown = cooldown_seconds
        self.failures = {} # key -> timestamp of last failure

    def can_try(self, key: str) -> bool:
        last_fail = self.failures.get(key, 0)
        if time.time() - last_fail > self.cooldown:
            return True
        return False

    def record_failure(self, key: str):
        self.failures[key] = time.time()

class LLMManager:
    def __init__(self):
        self.config = get_config()
        self.providers = self.config["llm"]["providers"]
        self.breaker = CircuitBreaker()
        self.run_budget = self.config["llm"]["global_run_budget"]
        self.calls_this_run = 0

    def generate(self, prompt: str) -> Optional[str]:
        if self.calls_this_run >= self.run_budget:
            logger.warning("LLM Budget exceeded for this run.")
            return None

        # Try providers in order
        for provider_conf in self.providers:
            p_name = provider_conf["name"]
            
            for model in provider_conf["models"]:
                breaker_key = f"{p_name}:{model}"
                
                if not self.breaker.can_try(breaker_key):
                    continue

                try:
                    logger.info(f"Attempting LLM call with {p_name} / {model}")
                    result = self._call_provider(p_name, model, prompt)
                    if result:
                        self.calls_this_run += 1
                        return result
                except Exception as e:
                    logger.error(f"LLM Failed {p_name}/{model}: {e}")
                    self.breaker.record_failure(breaker_key)
        
        return None

    def _call_provider(self, provider: str, model: str, prompt: str) -> str:
        if provider == "groq":
            return self._call_groq(model, prompt)
        elif provider == "openrouter":
            return self._call_openrouter(model, prompt)
        elif provider == "huggingface":
            return self._call_huggingface(model, prompt)
        else:
            raise ValueError(f"Unknown provider {provider}")

    def _call_groq(self, model: str, prompt: str) -> str:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key: raise ValueError("Missing Groq API Key")
        
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}", 
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.config["llm"]["max_output_tokens"]
        }
        
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        if resp.status_code == 429:
            raise Exception("Rate Limited")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_openrouter(self, model: str, prompt: str) -> str:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key: raise ValueError("Missing OpenRouter Key")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}", 
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/tech-job-finder", 
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.config["llm"]["max_output_tokens"]
        }
        
        resp = requests.post(url, headers=headers, json=data, timeout=15)
        if resp.status_code == 429:
            raise Exception("Rate Limited")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_huggingface(self, model: str, prompt: str) -> str:
        api_key = os.environ.get("HUGGINGFACE_API_KEY")
        if not api_key: raise ValueError("Missing HF Key")

        # HF Inference API usage
        url = f"https://api-inference.huggingface.co/models/{model}"
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "inputs": prompt, 
            "parameters": {"max_new_tokens": 150, "return_full_text": False}
        }
        
        resp = requests.post(url, headers=headers, json=data, timeout=20)
        if resp.status_code == 429:
            raise Exception("Rate Limited")
        resp.raise_for_status()
        
        # Output format varies for HF models, usually list of dicts
        res_json = resp.json()
        if isinstance(res_json, list) and "generated_text" in res_json[0]:
            return res_json[0]["generated_text"]
        return str(res_json)
