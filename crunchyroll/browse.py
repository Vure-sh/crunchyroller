"""
Módulo para obtener animes en emisión (Browse API).

Esta API devuelve los animes más recientes añadidos, populares, etc.
URL: https://www.crunchyroll.com/content/v2/discover/browse
"""

import time
from typing import Dict, Any, List, Optional
import requests

from .http_client import CrunchyrollHttpClient
from .config import get_api_browse_config


def get_browse_animes(
    client: CrunchyrollHttpClient,
    limit: int = None,
    sort_by: str = None,
    ratings: bool = None,
    locale: str = None,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Obtener animes en emisión desde la Browse API.

    Args:
        client: Instancia de CrunchyrollHttpClient con token autenticado.
        limit: Número máximo de resultados (default: 36).
        sort_by: Ordenación (newly_added, popular, etc.) (default: newly_added).
        ratings: Incluir solo animes con calificación (default: True).
        debug: Si True, imprime detalles de la respuesta en consola.

    Returns:
        Diccionario con los datos de la respuesta JSON.
    """
    # Usar valores por defecto si no se proporcionan
    if limit is None:
        limit = get_api_browse_config().get("limit", 36)
    if sort_by is None:
        sort_by = get_api_browse_config().get("sort_by", "newly_added")
    if ratings is None:
        ratings = get_api_browse_config().get("ratings", True)
    if locale is None:
        locale = "en-US"

    # Construir URL
    url = f"https://www.crunchyroll.com/content/v2/discover/browse"
    params = {
        "n": limit,
        "sort_by": sort_by,
        "ratings": str(ratings).lower(),
        "locale": locale,
    }
    url_with_params = f"{url}?{urlencode_params(params)}"

    started_at = time.monotonic()
    try:
        response = client.do_request("GET", url_with_params)
        response.raise_for_status()
        
        data = response.json()
        
        if debug:
            print("\n" + "="*60)
            print("[browse] Respuesta recibida:")
            print("="*60)
            print(f"Status Code: {response.status_code}")
            print(f"URL: {url_with_params}")
            print(f"Data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
            print(f"Total items: {data.get('total', 'N/A')}")
            print(f"Items returned: {len(data.get('data', [])) if isinstance(data.get('data'), list) else 'N/A'}")
            print("="*60 + "\n")
            
            # Mostrar resumen de cada anime
            items = data.get('data', [])
            if isinstance(items, list) and items:
                print("RESUMEN DE ANIMES:")
                print("-"*60)
                for i, item in enumerate(items[:5]):  # Mostrar solo los primeros 5
                    print(f"\n--- Anime {i+1} ---")
                    print(f"  ID: {item.get('id', 'N/A')}")
                    print(f"  Title: {item.get('title', 'N/A')}")
                    print(f"  Type: {item.get('type', 'N/A')}")
                    status = item.get('status', 'N/A')
                    print(f"  Status: {status}")
                    print(f"  Description: {item.get('description', 'N/A')[:150]}...")
        
        return data
        
    except requests.exceptions.HTTPError as e:
        if debug:
            print(f"\n[browse] Error HTTP: {e}")
            print(f"  Status: {e.response.status_code if e.response else 'N/A'}")
            print(f"  Response: {e.response.text[:500] if e.response else 'N/A'}")
        raise
    except requests.exceptions.RequestException as e:
        if debug:
            print(f"\n[browse] Error de solicitud: {e}")
        raise
    except Exception as e:
        if debug:
            print(f"\n[browse] Error inesperado: {type(e).__name__}: {e}")
        raise


def urlencode_params(params: Dict[str, Any]) -> str:
    """
    Codificar parámetros de URL manualmente (evitando problemas con requests).
    
    Args:
        params: Diccionario de parámetros.
    
    Returns:
        String de parámetros codificados.
    """
    parts = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = str(value).lower()
        elif isinstance(value, list):
            value = ",".join(str(v) for v in value)
        try:
            encoded_key = key.encode("utf-8").decode("ascii")
            encoded_value = str(value).encode("utf-8").decode("ascii")
            parts.append(f"{encoded_key}={encoded_value}")
        except UnicodeEncodeError:
            # Si falla, usar la representación original
            parts.append(f"{key}={value}")
    return "&".join(parts)