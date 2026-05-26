"""IIC-FORGE persona overlay system. See ADR-F3 + ADR-NEW-2 in the program design."""

from .loader import Persona, load_persona_from_string, load_all_personas

__all__ = ["Persona", "load_persona_from_string", "load_all_personas"]
