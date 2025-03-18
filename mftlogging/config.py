import json
import os

DEFAULT_CONFIG = {
        "prefix": "!",
        "admin_role": "Admin",
        "default_poll_duration":3600,
        "logging_level": "INFO"
}

CONFIG_FILE = "../config.json"

def load_config():
    """Loads the bot config file, and checks all needed values are there"""
    if not os.path.exists(CONFIG_FILE):
        print("Config file missing, creating default...")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    try:
        with open(CONFIG_FILE, "r") as c:
            config = json.load(c)

        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = value
                print(f"Missing Key: {key}\nAdding default to config...")

        return config

    except (json.JSONDecodeError, IOError) as e:
    print(f"Error loading config: {e}. Creating default config...")
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG

def save_config(config: str):
    """Saves conguration options to the config.file in the main directory"""
    try:
        with open(CONFIG_FILE, "w") as c:
            json.dump(config, f, indent=4)
        print("Config file updated.")

    except IOError as e:
        print(f"Failed to update config: {e}")

config = load_config()

