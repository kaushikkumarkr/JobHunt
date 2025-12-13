from typing import Optional
from storage.sheets_store import SheetsStore

class LLMCacheStore:
    def __init__(self, store: SheetsStore):
        self.store = store
        # In-memory cache to avoid repeated sheet reads in one run
        self._local_cache = {}

    def get(self, text_hash: str) -> Optional[str]:
        if text_hash in self._local_cache:
            return self._local_cache[text_hash]
        
        val = self.store.get_llm_cache_entry(text_hash)
        if val:
            self._local_cache[text_hash] = val
        return val

    def set(self, text_hash: str, output: str, model: str):
        self._local_cache[text_hash] = output
        self.store.save_llm_cache_entry(text_hash, output, model)
