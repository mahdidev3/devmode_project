\
MODE_SPECS = {
    "devmode1": {
        "app_name": "Devmode1",
        "listen_scheme": "http",
        "auth_enabled": True,
        "mode_kind": "direct",
        "env_prefix": "DEVMODE1",
    },
    "devmode2": {
        "app_name": "Devmode2",
        "listen_scheme": "https",
        "auth_enabled": True,
        "mode_kind": "direct",
        "env_prefix": "DEVMODE2",
    },
    "devmode3": {
        "app_name": "Devmode3",
        "listen_scheme": "http",
        "auth_enabled": False,
        "mode_kind": "direct",
        "env_prefix": "DEVMODE3",
    },
    "devmode4": {
        "app_name": "Devmode4",
        "listen_scheme": "https",
        "auth_enabled": False,
        "mode_kind": "direct",
        "env_prefix": "DEVMODE4",
    },
    "devmode5": {
        "app_name": "Devmode5",
        "listen_scheme": "http",
        "auth_enabled": False,
        "mode_kind": "tunnel",
        "env_prefix": "DEVMODE5",
    },
}

ORDERED_MODE_KEYS = ["devmode1", "devmode2", "devmode3", "devmode4", "devmode5"]
