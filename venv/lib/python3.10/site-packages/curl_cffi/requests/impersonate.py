import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional, TypedDict

from ..const import CurlOpt, CurlSslVersion
from ..utils import CurlCffiWarning

BrowserTypeLiteral = Literal[
    # Edge
    "edge99",
    "edge101",
    # Chrome
    "chrome99",
    "chrome100",
    "chrome101",
    "chrome104",
    "chrome107",
    "chrome110",
    "chrome116",
    "chrome119",
    "chrome120",
    "chrome123",
    "chrome124",
    "chrome131",
    "chrome133a",
    "chrome136",
    "chrome99_android",
    "chrome131_android",
    # Safari
    "safari153",
    "safari155",
    "safari170",
    "safari172_ios",
    "safari180",
    "safari180_ios",
    "safari184",
    "safari184_ios",
    "safari260",
    "safari260_ios",
    # Firefox
    "firefox133",
    "firefox135",
    "tor145",
    # alias
    "chrome",
    "edge",
    "safari",
    "safari_ios",
    "safari_beta",
    "safari_ios_beta",
    "chrome_android",
    "firefox",
    # deprecated aliases
    "safari15_3",
    "safari15_5",
    "safari17_0",
    "safari17_2_ios",
    "safari18_0",
    "safari18_0_ios",
    "safari18_4",
    "safari18_4_ios",
    # Canonical names
    # "edge_99",
    # "edge_101",
    # "safari_15.3_macos",
    # "safari_15.5_macos",
    # "safari_17.2_ios",
    # "safari_17.0_macos",
    # "safari_18.0_ios",
    # "safari_18.0_macos",
]


DEFAULT_CHROME = "chrome136"
DEFAULT_EDGE = "edge101"
DEFAULT_SAFARI = "safari184"
DEFAULT_SAFARI_IOS = "safari184_ios"
DEFAULT_SAFARI_BETA = "safari260"
DEFAULT_SAFARI_IOS_BETA = "safari260_ios"
DEFAULT_CHROME_ANDROID = "chrome131_android"
DEFAULT_FIREFOX = "firefox135"
DEFAULT_TOR = "tor145"


REAL_TARGET_MAP = {
    "chrome": "chrome136",
    "edge": "edge101",
    "safari": "safari184",
    "safari_ios": "safari184_ios",
    "safari_beta": "safari260",
    "safari_ios_beta": "safari260_ios",
    "chrome_android": "chrome131_android",
    "firefox": "firefox135",
    "tor": "tor145",
}


def normalize_browser_type(item):
    if item == "chrome":  # noqa: SIM116
        return DEFAULT_CHROME
    elif item == "edge":
        return DEFAULT_EDGE
    elif item == "safari":
        return DEFAULT_SAFARI
    elif item == "safari_ios":
        return DEFAULT_SAFARI_IOS
    elif item == "safari_beta":
        return DEFAULT_SAFARI_BETA
    elif item == "safari_ios_beta":
        return DEFAULT_SAFARI_IOS_BETA
    elif item == "chrome_android":
        return DEFAULT_CHROME_ANDROID
    elif item == "firefox":
        return DEFAULT_FIREFOX
    elif item == "tor":
        return DEFAULT_TOR
    else:
        return item


class BrowserType(str, Enum):  # TODO: remove in version 1.x
    edge99 = "edge99"
    edge101 = "edge101"
    chrome99 = "chrome99"
    chrome100 = "chrome100"
    chrome101 = "chrome101"
    chrome104 = "chrome104"
    chrome107 = "chrome107"
    chrome110 = "chrome110"
    chrome116 = "chrome116"
    chrome119 = "chrome119"
    chrome120 = "chrome120"
    chrome123 = "chrome123"
    chrome124 = "chrome124"
    chrome131 = "chrome131"
    chrome133a = "chrome133a"
    chrome136 = "chrome136"
    chrome99_android = "chrome99_android"
    chrome131_android = "chrome131_android"
    safari153 = "safari153"
    safari155 = "safari155"
    safari170 = "safari170"
    safari172_ios = "safari172_ios"
    safari180 = "safari180"
    safari180_ios = "safari180_ios"
    safari184 = "safari184"
    safari184_ios = "safari184_ios"
    safari260 = "safari260"
    safari260_ios = "safari260_ios"
    firefox133 = "firefox133"
    firefox135 = "firefox135"
    tor145 = "tor145"

    # deprecated aliases
    safari15_3 = "safari15_3"
    safari15_5 = "safari15_5"
    safari17_0 = "safari17_0"
    safari17_2_ios = "safari17_2_ios"
    safari18_0 = "safari18_0"
    safari18_0_ios = "safari18_0_ios"


@dataclass
class ExtraFingerprints:
    tls_min_version: int = CurlSslVersion.TLSv1_2
    tls_grease: bool = False
    tls_permute_extensions: bool = False
    tls_cert_compression: Literal["zlib", "brotli"] = "brotli"
    tls_signature_algorithms: Optional[list[str]] = None
    tls_delegated_credential: str = ""
    tls_record_size_limit: int = 0
    http2_stream_weight: int = 256
    http2_stream_exclusive: int = 1
    http2_no_priority: bool = False


class ExtraFpDict(TypedDict, total=False):
    tls_min_version: int
    tls_grease: bool
    tls_permute_extensions: bool
    tls_cert_compression: Literal["zlib", "brotli"]
    tls_signature_algorithms: Optional[list[str]]
    tls_delegated_credential: str
    tls_record_size_limit: int
    http2_stream_weight: int
    http2_stream_exclusive: int
    http2_no_priority: bool


# TLS version are in the format of 0xAABB, where AA is major version and BB is minor
# version. As of today, the major version is always 03.
TLS_VERSION_MAP = {
    0x0301: CurlSslVersion.TLSv1_0,  # 769
    0x0302: CurlSslVersion.TLSv1_1,  # 770
    0x0303: CurlSslVersion.TLSv1_2,  # 771
    0x0304: CurlSslVersion.TLSv1_3,  # 772
}

# A list of the possible cipher suite ids. Taken from
# http://www.iana.org/assignments/tls-parameters/tls-parameters.xml
# via BoringSSL
TLS_CIPHER_NAME_MAP = {
    0x000A: "TLS_RSA_WITH_3DES_EDE_CBC_SHA",
    0x002F: "TLS_RSA_WITH_AES_128_CBC_SHA",
    0x0033: "TLS_DHE_RSA_WITH_AES_128_CBC_SHA",
    0x0035: "TLS_RSA_WITH_AES_256_CBC_SHA",
    0x0039: "TLS_DHE_RSA_WITH_AES_256_CBC_SHA",
    0x003C: "TLS_RSA_WITH_AES_128_CBC_SHA256",
    0x003D: "TLS_RSA_WITH_AES_256_CBC_SHA256",
    0x0067: "TLS_DHE_RSA_WITH_AES_128_CBC_SHA256",
    0x006B: "TLS_DHE_RSA_WITH_AES_256_CBC_SHA256",
    0x008C: "TLS_PSK_WITH_AES_128_CBC_SHA",
    0x008D: "TLS_PSK_WITH_AES_256_CBC_SHA",
    0x009C: "TLS_RSA_WITH_AES_128_GCM_SHA256",
    0x009D: "TLS_RSA_WITH_AES_256_GCM_SHA384",
    0x009E: "TLS_DHE_RSA_WITH_AES_128_GCM_SHA256",
    0x009F: "TLS_DHE_RSA_WITH_AES_256_GCM_SHA384",
    0x1301: "TLS_AES_128_GCM_SHA256",
    0x1302: "TLS_AES_256_GCM_SHA384",
    0x1303: "TLS_CHACHA20_POLY1305_SHA256",
    0xC008: "TLS_ECDHE_ECDSA_WITH_3DES_EDE_CBC_SHA",
    0xC009: "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA",
    0xC00A: "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA",
    0xC012: "TLS_ECDHE_RSA_WITH_3DES_EDE_CBC_SHA",
    0xC013: "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA",
    0xC014: "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA",
    0xC023: "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA256",
    0xC024: "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA384",
    0xC027: "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256",
    0xC028: "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA384",
    0xC02B: "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
    0xC02C: "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
    0xC02F: "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
    0xC030: "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
    0xC035: "TLS_ECDHE_PSK_WITH_AES_128_CBC_SHA",
    0xC036: "TLS_ECDHE_PSK_WITH_AES_256_CBC_SHA",
    0xCCA8: "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256",
    0xCCA9: "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256",
    0xCCAC: "TLS_ECDHE_PSK_WITH_CHACHA20_POLY1305_SHA256",
}


# RFC tls extensions: https://datatracker.ietf.org/doc/html/rfc6066
# IANA list: https://www.iana.org/assignments/tls-extensiontype-values/tls-extensiontype-values.xhtml
TLS_EXTENSION_NAME_MAP = {
    0: "server_name",
    1: "max_fragment_length",
    2: "client_certificate_url",
    3: "trusted_ca_keys",
    4: "truncated_hmac",
    5: "status_request",
    6: "user_mapping",
    7: "client_authz",
    8: "server_authz",
    9: "cert_type",
    10: "supported_groups",  # (renamed from "elliptic_curves")
    11: "ec_point_formats",
    12: "srp",
    13: "signature_algorithms",
    14: "use_srtp",
    15: "heartbeat",
    16: "application_layer_protocol_negotiation",
    17: "status_request_v2",
    18: "signed_certificate_timestamp",
    19: "client_certificate_type",
    20: "server_certificate_type",
    21: "padding",
    22: "encrypt_then_mac",
    23: "extended_master_secret",
    24: "token_binding",
    25: "cached_info",
    26: "tls_lts",
    27: "compress_certificate",
    28: "record_size_limit",
    29: "pwd_protect",
    30: "pwd_clear",
    31: "password_salt",
    32: "ticket_pinning",
    33: "tls_cert_with_extern_psk",
    34: "delegated_credential",
    35: "session_ticket",  # (renamed from "SessionTicket TLS")
    36: "TLMSP",
    37: "TLMSP_proxying",
    38: "TLMSP_delegate",
    39: "supported_ekt_ciphers",
    # 40:"Reserved",
    41: "pre_shared_key",
    42: "early_data",
    43: "supported_versions",
    44: "cookie",
    45: "psk_key_exchange_modes",
    # 46:"Reserved",
    47: "certificate_authorities",
    48: "oid_filters",
    49: "post_handshake_auth",
    50: "signature_algorithms_cert",
    51: "key_share",
    52: "transparency_info",
    # 53:"connection_id", # (deprecated)
    54: "connection_id",
    55: "external_id_hash",
    56: "external_session_id",
    57: "quic_transport_parameters",
    58: "ticket_request",
    59: "dnssec_chain",
    60: "sequence_number_encryption_algorithms",
    61: "rrc",
    17513: "application_settings",  # BoringSSL private usage
    17613: "application_settings new",  # BoringSSL private usage
    # 62-2569:"Unassigned
    # 2570:"Reserved
    # 2571-6681:"Unassigned
    # 6682:"Reserved
    # 6683-10793:"Unassigned
    # 10794:"Reserved
    # 10795-14905:"Unassigned
    # 14906:"Reserved
    # 14907-19017:"Unassigned
    # 19018:"Reserved
    # 19019-23129:"Unassigned
    # 23130:"Reserved
    # 23131-27241:"Unassigned
    # 27242:"Reserved
    # 27243-31353:"Unassigned
    # 31354:"Reserved
    # 31355-35465:"Unassigned
    # 35466:"Reserved
    # 35467-39577:"Unassigned
    # 39578:"Reserved
    # 39579-43689:"Unassigned
    # 43690:"Reserved
    # 43691-47801:"Unassigned
    # 47802:"Reserved
    # 47803-51913:"Unassigned
    # 51914:"Reserved
    # 51915-56025:"Unassigned
    # 56026:"Reserved
    # 56027-60137:"Unassigned
    # 60138:"Reserved
    # 60139-64249:"Unassigned
    # 64250:"Reserved
    # 64251-64767:"Unassigned
    64768: "ech_outer_extensions",
    # 64769-65036:"Unassigned
    65037: "encrypted_client_hello",
    # 65038-65279:"Unassigned
    # 65280:"Reserved for Private Use
    65281: "renegotiation_info",
    # 65282-65535:"Reserved for Private Use
}


TLS_EC_CURVES_MAP = {
    19: "P-192",
    21: "P-224",
    23: "P-256",
    24: "P-384",
    25: "P-521",
    29: "X25519",
    256: "ffdhe2048",
    257: "ffdhe3072",
    4588: "X25519MLKEM768",
    25497: "X25519Kyber768Draft00",
}


def toggle_extension(curl, extension_id: int, enable: bool):
    # ECH
    if extension_id == 65037:
        if enable:
            curl.setopt(CurlOpt.ECH, "grease")
        else:
            curl.setopt(CurlOpt.ECH, "")
    # compress certificate
    elif extension_id == 27:
        if enable:
            warnings.warn(
                "Cert compression setting to brotli, "
                "you had better specify which to use: zlib/brotli",
                CurlCffiWarning,
                stacklevel=1,
            )
            curl.setopt(CurlOpt.SSL_CERT_COMPRESSION, "brotli")
        else:
            curl.setopt(CurlOpt.SSL_CERT_COMPRESSION, "")
    # ALPS: application settings
    elif extension_id == 17513:
        if enable:
            curl.setopt(CurlOpt.SSL_ENABLE_ALPS, 1)
        else:
            curl.setopt(CurlOpt.SSL_ENABLE_ALPS, 0)
    elif extension_id == 17613:
        if enable:
            curl.setopt(CurlOpt.SSL_ENABLE_ALPS, 1)
            curl.setopt(CurlOpt.TLS_USE_NEW_ALPS_CODEPOINT, 1)
        else:
            curl.setopt(CurlOpt.SSL_ENABLE_ALPS, 0)
            curl.setopt(CurlOpt.TLS_USE_NEW_ALPS_CODEPOINT, 0)
    # server_name
    elif extension_id == 0:
        raise NotImplementedError(
            "It's unlikely that the server_name(0) extension being changed."
        )
    # ALPN
    elif extension_id == 16:
        if enable:
            curl.setopt(CurlOpt.SSL_ENABLE_ALPN, 1)
        else:
            curl.setopt(CurlOpt.SSL_ENABLE_ALPN, 0)
    # status_request
    elif extension_id == 5:
        if enable:
            curl.setopt(CurlOpt.TLS_STATUS_REQUEST, 1)
    # signed_certificate_timestamps
    elif extension_id == 18:
        if enable:
            curl.setopt(CurlOpt.TLS_SIGNED_CERT_TIMESTAMPS, 1)
    # session_ticket
    elif extension_id == 35:
        if enable:
            curl.setopt(CurlOpt.SSL_ENABLE_TICKET, 1)
        else:
            curl.setopt(CurlOpt.SSL_ENABLE_TICKET, 0)
    # padding, should be ignored
    elif extension_id == 21:
        pass  # type: ignore
    # firefox extension, toggled by extra_fp
    elif extension_id in [34, 28]:
        pass
    else:
        raise NotImplementedError(
            f"This extension({extension_id}) can not be toggled for now, it may be "
            "updated later."
        )
