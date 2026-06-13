"""India-specific sector research checklists."""

from __future__ import annotations


SECTOR_CHECKLISTS: dict[str, list[str]] = {
    "pharma": [
        "USFDA inspections",
        "ANDA pipeline",
        "API/intermediates exposure",
        "US generics price erosion",
        "India branded formulations growth",
        "chronic/acute mix",
        "biosimilars",
        "R&D intensity",
        "plant warning letters/import alerts",
        "currency sensitivity",
    ],
    "chemicals": [
        "China pricing/dumping",
        "inventory destocking/restocking",
        "specialty vs commodity mix",
        "agrochemical cycle",
        "fluorination",
        "capex commissioning",
        "working capital intensity",
        "environmental clearances",
        "export exposure",
    ],
    "oil_gas": [
        "crude/Brent",
        "GRM",
        "marketing margins",
        "OMC under-recoveries",
        "gas transmission volume",
        "LNG prices",
        "APM gas policy",
        "windfall tax if relevant",
        "inventory gains/losses",
        "capex pipelines/refining/petrochem",
    ],
    "banks_nbfc": [
        "credit growth",
        "deposit growth",
        "NIM",
        "CASA mix",
        "GNPA/NNPA",
        "credit cost",
        "LCR",
        "RBI policy sensitivity",
        "unsecured lending exposure",
    ],
    "it_services": [
        "deal wins",
        "large-deal TCV",
        "BFSI demand",
        "attrition",
        "utilization",
        "pricing",
        "margin levers",
        "USD/INR sensitivity",
    ],
    "autos": ["volume growth", "EV mix", "commodity costs", "discounting", "dealer inventory", "rural demand"],
    "cement": ["capacity additions", "utilization", "power/fuel cost", "regional pricing", "freight"],
    "metals": ["China demand", "spreads", "iron ore/coking coal", "export duties", "leverage"],
    "consumer": ["volume growth", "rural demand", "gross margin", "ad spend", "channel inventory"],
    "utilities_power": ["PLF", "merchant tariffs", "coal availability", "receivables", "regulated equity"],
}

ALIASES = {
    "pharmaceuticals": "pharma",
    "chemical": "chemicals",
    "oil & gas": "oil_gas",
    "oil and gas": "oil_gas",
    "banks": "banks_nbfc",
    "nbfc": "banks_nbfc",
    "it": "it_services",
    "power": "utilities_power",
    "utilities": "utilities_power",
}


def normalize_sector(sector: str | None) -> str | None:
    if not sector:
        return None
    key = sector.strip().lower().replace(" ", "_").replace("-", "_")
    return ALIASES.get(key, key)


def get_sector_checklist(sector: str | None) -> list[str]:
    key = normalize_sector(sector)
    if key and key in SECTOR_CHECKLISTS:
        return SECTOR_CHECKLISTS[key]
    return [
        "revenue growth",
        "margin trend",
        "working capital",
        "capex",
        "leverage",
        "regulatory risk",
        "currency sensitivity",
        "promoter/FII/DII shareholding",
    ]


def render_sector_context(symbol: str, sector: str | None = None) -> str:
    checklist = get_sector_checklist(sector)
    rows = "\n".join(f"- {item}" for item in checklist)
    label = normalize_sector(sector) or "general_india"
    return f"# India Sector Context: {label}\n\nSymbol: {symbol}\n\nChecklist:\n{rows}"
