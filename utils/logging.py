import logging
import sys
import os

def setup_logging(level=logging.INFO):
    """
    Setup logging configuration.
    """
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    handlers = [
        logging.StreamHandler(sys.stdout)
    ]
    
    # Optional: File handler
    # log_file = "app.log"
    # handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=handlers
    )
    
    # Quiet down some noisy libraries
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("oauth2client").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    return logging.getLogger("TechJobFinder")
