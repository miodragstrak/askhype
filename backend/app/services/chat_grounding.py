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

_CYRILLIC = dict(zip(
    "абвгдђежзијклљмнњопрстћуфхцчџш",
    ("a", "b", "v", "g", "d", "dj", "e", "z", "z", "i", "j", "k", "l", "lj",
     "m", "n", "nj", "o", "p", "r", "s", "t", "c", "u", "f", "h", "c", "c", "dz", "s"),
))
_CYRILLIC_TRANSLATION = str.maketrans(_CYRILLIC)
_SEARCH = re.compile(
    r"\b(?:pretrazi(?:te)? (?:internet|web|veb)|(?:pronadji|proveri|provjeri)(?:te)?\b.{0,40}\bna internetu"
    r"|search (?:the )?(?:web|internet)|look up\b.{0,60}\bonline|look up online)\b"
)
_NON_FACTUAL = re.compile(
    r"^(?:(?:please|molim te) )?(?:write|translate|calculate|imagine|suppose|pretend|"
    r"napisi|prevedi|izracunaj|zamisli|pretpostavi|what if|sta ako)\b"
)
_TIME = re.compile(
    r"\b(?:veceras|ovog vikenda|(?:sledeceg|sljedeceg|narednog) vikenda|ovog meseca|ovog mjeseca|"
    r"this weekend|next weekend|this month|tonight|uskoro|upcoming)\b|"
    r"\b\d{1,2}\.\s*(?:i \d{1,2}\.\s*)?(?:januar|februar|mart|april|maj|jun|jul|avgust|"
    r"septemb|oktob|novemb|decemb)\w*\b|"
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december) \d{1,2}\b"
)
_EVENT = re.compile(r"\b(?:dogadjaj\w*|koncer(?:t\w*|ata)|izlozb\w*|festival\w*|bioskop\w*|kino|"
                    r"events?|concerts?|exhibitions?|festivals?|cinema)\b")
_LIVE_TOPIC = re.compile(r"\b(?:prices?|cen\w+|cijen\w+|market|trzist\w*|akcij\w*|stocks?|"
                         r"hours|radno vreme|radno vrijeme|otvoren\w*|open|closes?|"
                         r"ceo|presidenti|predsedni\w*|predsjedni\w*|premijer\w*|developments|desavanj\w*|"
                         r"dostup\w*|available|score|rezultat\w*|schedule|raspored\w*)\b")


def _normalized_text(message: str) -> str:
    folded = message.casefold().translate(_CYRILLIC_TRANSLATION).replace("đ", "dj")
    decomposed = unicodedata.normalize("NFKD", folded)
    return " ".join(
        "".join(character for character in decomposed if not unicodedata.combining(character)).split()
    )


def decide_chat_grounding(message: str) -> GroundingDecision:
    normalized = _normalized_text(message)
    if _NON_FACTUAL.search(normalized):
        return GroundingDecision(False)
    if _SEARCH.search(normalized):
        return GroundingDecision(True, "explicit_search")
    relative = re.search(_CATEGORY_PATTERNS[-1][1], normalized) or _TIME.search(normalized)
    if _EVENT.search(normalized) and (relative or re.search(
        r"\b(?:koji se odrzavaju|sta se odrzava|ima li|what(?:'s| is) on|are there any)\b", normalized,
    )):
        return GroundingDecision(True, "events")
    if relative and _LIVE_TOPIC.search(normalized):
        return GroundingDecision(True, "current_information")
    if re.search(r"\b(?:kada (?:se )?(?:otvara|zatvara)|what time (?:does|do)|"
                 r"opening hours|radno vrem[ej]e|ko (?:vodi|je na celu)|who (?:runs|leads))\b", normalized):
        return GroundingDecision(True, "hours_or_leadership")
    if re.search(r"^(?:what is|sta je|objasni|explain|how does|kako radi)\b", normalized) and not relative:
        return GroundingDecision(False)
    for category, pattern in _CATEGORY_PATTERNS:
        if category == "relative_time":
            continue
        if re.search(pattern, normalized):
            return GroundingDecision(True, category)
    return GroundingDecision(False)
