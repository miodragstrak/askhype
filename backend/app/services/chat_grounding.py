import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class GroundingDecision:
    enabled: bool
    category: str | None = None


_CATEGORY_PATTERNS = (
    ("weather", r"\b(?:weather|forecast|prognoz\w*|vreme|vrijeme|vremensk\w*|meteo|wetter|m[eé]t[eé]o|tempo|moti)\b"),
    ("news", r"\b(?:news|latest news|novost\w*|vest\w*|vijest\w*|lajm\w*|nachrichten|actualit[eé]s|notizie|noticias)\b"),
    ("prices", r"\b(?:price|prices|costs? today|cen[aeiu]?|cijena\w*|preis\w*|prix|prezz\w*|precio\w*)\b"),
    ("schedules", r"\b(?:schedule|timetable|departure|arrival|red voznje|polazak|dolazak|raspored\w*|fahrplan|horaire\w*|orari\w*|horario\w*)\b"),
    ("sports", r"\b(?:score|scores|result(?:s)?|rezultat\w*|utakmic\w*|standings|tabela|spielstand|r[eé]sultat\w*|risultat\w*)\b"),
    ("rates", r"\b(?:exchange rate|currency rate|kurs\w*|tecaj\w*|wechselkurs|taux de change|tasso di cambio|tipo de cambio)\b"),
    ("availability", r"\b(?:available now|availability|in stock|dostupn\w*|na stanju|verfugbar|disponible|disponibil\w*)\b"),
    ("current_role", r"\b(?:who is (?:the )?(?:current|president|prime minister|ceo)|ko je (?:trenutn\w* )?(?:predsednik|predsjednik|premijer|direktor)|president\w* aktual\w*|aktuelle\w* prasident\w*)\b"),
    ("relative_time", r"\b(?:today|tomorrow|yesterday|now|currently|latest|current|this week|danas|sutra|juce|trenutno|najnovij\w*|aktueln\w*|ove nedelje|ove sedmice|sot|neser|aktual\w*|heute|morgen|gestern|derzeit|aujourd'hui|demain|actuel\w*|oggi|domani|attual\w*|hoy|manana|actual\w*)\b"),
)


def _normalized_text(message: str) -> str:
    decomposed = unicodedata.normalize("NFKD", message.casefold())
    return " ".join(
        "".join(character for character in decomposed if not unicodedata.combining(character)).split()
    )


def decide_chat_grounding(message: str) -> GroundingDecision:
    normalized = _normalized_text(message)
    for category, pattern in _CATEGORY_PATTERNS:
        if re.search(pattern, normalized):
            return GroundingDecision(True, category)
    return GroundingDecision(False)
