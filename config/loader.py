import os
import yaml
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class ConfigLoader:
    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
            cls._instance.load_config()
        return cls._instance

    def load_config(self, config_path: str = "config/config.yaml"):
        """Load configuration from a YAML file."""
        # Check if running in a place where config file might be elsewhere (e.g. tests)
        if not os.path.exists(config_path):
             # Fallback for dev/test environments
             base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
             config_path = os.path.join(base_path, "config", "config.yaml")
        
        # If still not found, try example
        if not os.path.exists(config_path):
            example_path = config_path + ".example"
            if os.path.exists(example_path):
                logger.warning(f"Config file not found at {config_path}. Loading example config from {example_path}")
                config_path = example_path
            else:
                raise FileNotFoundError(f"Config file not found at {config_path} or {example_path}")

        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)
        
        # Override with environment variables if needed (minimal overrides for secrets)
        self._inject_secrets()

    def _inject_secrets(self):
        """Inject secrets from environment variables into config logic if needed."""
        # Secrets are largely handled by direct os.environ calls in specific modules, 
        # but we can map them here if we want a unified view.
        # For now, we trust the modules to look up os.getenv("SECRET_NAME")
        pass

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

# Global accessor
def get_config() -> Dict[str, Any]:
    return ConfigLoader().config
