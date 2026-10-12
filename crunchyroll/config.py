"""
Configuración de la aplicación.

Este archivo contiene todas las configuraciones de la aplicación,
incluyendo idiomas, calidades, y otras opciones.
"""

import json
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")


def load_config(config_path: str = None) -> dict:
    """
    Cargar configuración desde archivo JSON.
    
    Args:
        config_path: Ruta al archivo de configuración. Si None, usa CONFIG_FILE.
    
    Returns:
        Diccionario con la configuración cargada.
    """
    target_path = config_path or CONFIG_FILE
    config = {}
    
    if not os.path.exists(target_path):
        return config
    
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    
    return config


def save_config(config_dict: dict, config_path: str = None) -> None:
    """
    Guardar configuración en archivo JSON.
    
    Args:
        config_dict: Diccionario con la configuración a guardar.
        config_path: Ruta al archivo de configuración. Si None, usa CONFIG_FILE.
    """
    target_path = config_path or CONFIG_FILE
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(config_dict, f, indent=4, ensure_ascii=False)


# Configuración por defecto
DEFAULT_CONFIG = {
    # Idiomas
    "audio_language": "ja-JP",  # Idioma de audio por defecto
    "subtitle_language": "en-US",  # Idioma de subtítulos por defecto
    
    # Calidades
    "video_quality": "1080p",  # 1080p, 720p, 480p, 360p, none
    "audio_quality": "192k",  # 192k, 96k
    
    # Opciones
    "force_download": False,
    "enable_logging": True,
    "bitrate_mode": None,  # highest, lowest, best, data_saver
    
    # API
    "api": {
        "browse": {
            "limit": 36,  # Número de resultados por página
            "sort_by": "newly_added",  # newly_added, popular, etc.
            "ratings": True,  # Incluir solo animes con calificación
        }
    }
}


def get_config() -> dict:
    """
    Obtener configuración actual, usando valores por defecto si no existen.
    
    Returns:
        Diccionario con la configuración actual.
    """
    config = load_config()
    
    # Fusionar con valores por defecto
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value
    
    return config


def get_audio_language() -> str:
    """Obtener idioma de audio configurado."""
    config = get_config()
    return config.get("audio_language", "ja-JP")


def get_subtitle_language() -> str:
    """Obtener idioma de subtítulos configurado."""
    config = get_config()
    return config.get("subtitle_language", "en-US")


def get_video_quality() -> str:
    """Obtener calidad de video configurada."""
    config = get_config()
    return config.get("video_quality", "1080p")


def get_audio_quality() -> str:
    """Obtener calidad de audio configurada."""
    config = get_config()
    return config.get("audio_quality", "192k")


def get_bitrate_mode() -> str:
    """Obtener modo de bitrate configurado."""
    config = get_config()
    return config.get("bitrate_mode")


def get_api_browse_config() -> dict:
    """Obtener configuración de la API browse."""
    config = get_config()
    return config.get("api", {}).get("browse", {
        "limit": 36,
        "sort_by": "newly_added",
        "ratings": True,
    })