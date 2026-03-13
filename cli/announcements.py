import getpass
import requests
from rich.console import Console
from rich.panel import Panel
from urllib.parse import urlparse

from cli.config import CLI_CONFIG

# Whitelist of allowed domains for announcements
ALLOWED_ANNOUNCEMENT_DOMAINS = {'api.tauric.ai', 'tauric.ai'}
ALLOWED_SCHEMES = {'https'}


def validate_announcement_url(url: str) -> bool:
    """Validate that announcement URL is safe and from allowed domain.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid
        
    Raises:
        ValueError: If URL is invalid or not allowed
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}")
    
    # Check scheme
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Only {ALLOWED_SCHEMES} schemes allowed, got: {parsed.scheme}")
    
    # Check domain
    if parsed.hostname not in ALLOWED_ANNOUNCEMENT_DOMAINS:
        raise ValueError(
            f"Domain not allowed. Permitted domains: {ALLOWED_ANNOUNCEMENT_DOMAINS}, "
            f"got: {parsed.hostname}"
        )
    
    # Prevent localhost/internal IPs
    if parsed.hostname in ('localhost', '127.0.0.1', '0.0.0.0') or \
       parsed.hostname.startswith('192.168.') or \
       parsed.hostname.startswith('10.') or \
       parsed.hostname.startswith('172.'):
        raise ValueError("Internal/localhost URLs not allowed")
    
    return True


def fetch_announcements(url: str = None, timeout: float = None) -> dict:
    """Fetch announcements from endpoint. Returns dict with announcements and settings."""
    endpoint = url or CLI_CONFIG["announcements_url"]
    timeout = timeout or CLI_CONFIG["announcements_timeout"]
    fallback = CLI_CONFIG["announcements_fallback"]

    try:
        # Validate URL before making request
        validate_announcement_url(endpoint)
        response = requests.get(endpoint, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return {
            "announcements": data.get("announcements", [fallback]),
            "require_attention": data.get("require_attention", False),
        }
    except ValueError as e:
        # URL validation failed - security issue
        return {
            "announcements": [f"[red]Security Error:[/red] {str(e)}", fallback],
            "require_attention": False,
        }
    except Exception:
        return {
            "announcements": [fallback],
            "require_attention": False,
        }


def display_announcements(console: Console, data: dict) -> None:
    """Display announcements panel. Prompts for Enter if require_attention is True."""
    announcements = data.get("announcements", [])
    require_attention = data.get("require_attention", False)

    if not announcements:
        return

    content = "\n".join(announcements)

    panel = Panel(
        content,
        border_style="cyan",
        padding=(1, 2),
        title="Announcements",
    )
    console.print(panel)

    if require_attention:
        getpass.getpass("Press Enter to continue...")
    else:
        console.print()
