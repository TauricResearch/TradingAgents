from importlib import metadata

from .curl import Curl

__title__ = "curl_cffi"
__description__ = metadata.metadata("curl_cffi")["Summary"]
__version__ = metadata.version("curl_cffi")
__curl_version__ = Curl().version().decode()
