
import logging
import os
from pathlib import Path

def setup_logger(name: str, log_file: str = "trading_agents.log", level=logging.INFO):
    """Function to setup a logger; can be called multiple times for different loggers."""
    
    # Check if this logger already exists to avoid duplicate handlers
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
        
    logger.setLevel(level)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console Handler (Optional - Commented out to keep CLI clean)
    # ch = logging.StreamHandler()
    # ch.setFormatter(formatter)
    # logger.addHandler(ch)
    
    # File Handler
    try:
        # Create logs directory if it doesn't exist? 
        # For now, keep in root or specific path. 
        # Using current working directory for simplicity as requested.
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except IOError as e:
        print(f"Error setting up logger file handler: {e}")

    return logger

# Create main system logger
app_logger = setup_logger("TradingAgents", "agent.log")
# Create override specific logger
override_logger = setup_logger("OverrideLogic", "agent.log")
