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

    def score_lead(self, lead) -> 'JobLead':
        """
        Uses LLM to analyze the full job description and score it.
        Updates lead.match_score and lead.notes.
        """
        # Safety check
        if not lead.full_description:
            logger.warning(f"Skipping LLM score for {lead.lead_id} (No description)")
            return lead

        prompt = f"""
        You are an expert Tech Recruiter. Analyze this job post for a "Software Engineer" or "Product Manager" role.
        
        Job Title: {lead.role_title}
        Company: {lead.company}
        Location: {lead.city}, {lead.country}
        
        FULL DESCRIPTION:
        {lead.full_description[:6000]}  # Truncate to avoid context limits
        
        ---
        Your Task:
        1. Rate this job from 0.0 to 1.0 based on relevance to a modern Tech/Engineering role.
           - 1.0 = Perfect match (Engineering, Product, Data)
           - 0.0 = Smap, Consultant spam, Non-tech, or Irrelevant.
        2. Provide a 1-sentence reason.
        
        Return STRICT JSON format:
        {{
            "score": 0.95,
            "reason": "Strong match for Senior Backend role with Python usage."
        }}
        """
        
        try:
            response_text = self.generate(prompt)
            if not response_text:
                return lead
                
            # Clean response (remove markdown fences if present)
            clean_text = response_text.strip().replace("```json", "").replace("```", "")
            
            import json
            data = json.loads(clean_text)
            
            # Update Lead
            lead.match_score = float(data.get("score", lead.match_score))
            lead.notes = f"LLM: {data.get('reason', 'No reason provided')}"
            
            return lead
            
        except Exception as e:
            logger.error(f"Error parsing LLM response for {lead.lead_id}: {e}")
            return lead
    def generate_search_queries(self, roles: List[str], intent_phrases: str) -> List[str]:
        """
        Generates creative, dynamic boolean queries to find hidden gems.
        """
        try:
            roles_str = ", ".join(roles[:3]) # Context
            prompt = f"""
            Act as an expert Tech Sourcer (Headhunter).
            Your goal is to find hidden job posts on LinkedIn that standard keyword searches miss.
            
            Standard Query: site:linkedin.com/posts {intent_phrases} ({roles_str})
            
            Task:
            Generate 3 ALTERNATIVE, CREATIVE boolean search queries to find the same roles but using different "signals".
            Examples of signals:
            - "Series A funding"
            - "stealth mode"
            - "founding engineer"
            - "legacy code" (hiring to fix it)
            - "greenfield project"
            
            Return ONLY a raw JSON list of strings. DO NOT explain.
            Example:
            [
                "site:linkedin.com/posts \"stealth mode\" AND (\"hiring\" OR \"join us\") AND \"backend\"",
                "site:linkedin.com/posts \"greenfield\" AND \"engineer\" AND \"hiring\""
            ]
            """
            
            resp = self.generate(prompt)
            if not resp: return []
            
            import json
            import re
            
            # Clean response (remove markdown fences if present)
            clean_text = resp.strip()
            # aggressive cleanup
            if "```" in clean_text:
                clean_text = clean_text.split("```json")[-1].split("```")[0].strip()
            
            # Attempt to find list pattern [ ... ]
            list_match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if list_match:
                clean_text = list_match.group(0)

            try:
                queries = json.loads(clean_text)
            except json.JSONDecodeError:
                # Fallback: simple line split if JSON fails
                logger.warning("JSON parse failed for queries, using line split fallback")
                queries = [line.strip().strip('"').strip(',') for line in clean_text.split('\n') if "site:" in line]

            if isinstance(queries, list):
                logger.info(f"🧠 LLM Generated {len(queries)} dynamic queries.")
                return queries[:3] # Limit to 3 to be safe
                
            return []
            
        except Exception as e:
            logger.error(f"Failed to generate dynamic queries: {e}")
            return []
