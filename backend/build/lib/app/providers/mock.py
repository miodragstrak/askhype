from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from app.schemas.chat import ChatRequest, ChatResponse, Recommendation, SourceReference


MOCK_GENERATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
MOCK_LAST_VERIFIED = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


class MockAIProvider:
    provider_name = "mock"

    async def generate_chat_response(self, request: ChatRequest) -> ChatResponse:
        scenario = self._detect_scenario(request.message)
        conversation_id = request.conversation_id or self._conversation_id(request)

        if scenario == "travel":
            summary, recommendations, actions = self._travel_response(request)
        elif scenario == "food":
            summary, recommendations, actions = self._food_response(request)
        elif scenario == "nightlife":
            summary, recommendations, actions = self._nightlife_response(request)
        else:
            summary, recommendations, actions = self._fallback_response(request)

        return ChatResponse(
            conversation_id=conversation_id,
            provider=self.provider_name,
            answer_type="recommendations",
            summary=summary,
            recommendations=recommendations,
            follow_up_actions=actions,
            sources=self._sources(),
            generated_at=MOCK_GENERATED_AT,
        )

    def _detect_scenario(self, message: str) -> str:
        normalized = message.casefold()
        if self._has_any(
            normalized,
            ["putovanje", "vikend putovanje", "more", "planina", "crna gora", "hrvatska", "balkan"],
        ):
            return "travel"
        if self._has_any(normalized, ["restoran", "hrana", "ručak", "rucak", "večera", "vecera", "jesti"]):
            return "food"
        if self._has_any(
            normalized,
            ["izaći", "izaci", "izlazak", "večeras", "veceras", "koncert", "događaj", "dogadjaj", "vikend"],
        ):
            return "nightlife"
        return "fallback"

    def _nightlife_response(
        self, request: ChatRequest
    ) -> tuple[str, list[Recommendation], list[str]]:
        location = request.location
        interests = self._interest_phrase(request)
        return (
            f"Za {location} bih krenuo sa tri opcije koje pokrivaju muziku, dobru atmosferu i malo kulture"
            f"{interests}.",
            [
                Recommendation(
                    id="nightlife-koncert-01",
                    title="Koncert u centru grada",
                    category="koncert",
                    short_description="Veče sa živom muzikom i publikom koja dolazi zbog atmosfere, ne samo zbog pića.",
                    location=location,
                    estimated_price="1.200-2.500 RSD",
                    date_or_duration="ovog vikenda",
                    reason="Dobar izbor ako želiš energičan izlazak bez previše planiranja.",
                    image_url="https://example.com/images/askhype-koncert.jpg",
                    source_url="https://example.com/events/concert",
                ),
                Recommendation(
                    id="nightlife-live-music-02",
                    title="Restoran sa živom muzikom",
                    category="restoran",
                    short_description="Opuštena večera koja se kasnije pretvara u izlazak, sa lokalnim repertoarom.",
                    location=location,
                    estimated_price="2.000-4.000 RSD po osobi",
                    date_or_duration="večernji termin",
                    reason="Radi za društvo koje želi hranu, razgovor i muziku na istom mestu.",
                    image_url="https://example.com/images/askhype-live-music.jpg",
                    source_url="https://example.com/places/live-music",
                ),
                Recommendation(
                    id="nightlife-culture-03",
                    title="Kulturni događaj pred izlazak",
                    category="događaj",
                    short_description="Izložba, projekcija ili mali performans kao pametan početak večeri.",
                    location=location,
                    estimated_price="besplatno-1.000 RSD",
                    date_or_duration="60-90 minuta",
                    reason="Daje večeri bolju priču pre bara ili kluba.",
                    image_url="https://example.com/images/askhype-culture.jpg",
                    source_url="https://example.com/events/culture",
                ),
            ],
            [
                "Filtriraj samo događaje za večeras",
                "Dodaj opcije za mirniji izlazak",
                "Predloži plan po satima",
            ],
        )

    def _travel_response(
        self, request: ChatRequest
    ) -> tuple[str, list[Recommendation], list[str]]:
        interests = self._interest_phrase(request)
        return (
            f"Ako krećeš iz {request.location}, ovo su tri balkanske ideje za putovanje koje dobro rade za kraći beg"
            f"{interests}.",
            [
                Recommendation(
                    id="travel-kotor-01",
                    title="Kotor",
                    category="putovanje",
                    short_description="Stari grad, zaliv i lagan ritam za vikend uz more u Crnoj Gori.",
                    location="Kotor, Crna Gora",
                    estimated_price="srednji budžet",
                    date_or_duration="2-3 dana",
                    reason="Najbolji izbor ako želiš more, istoriju i lepe šetnje bez previše komplikovanja.",
                    image_url="https://example.com/images/askhype-kotor.jpg",
                    source_url="https://example.com/travel/kotor",
                ),
                Recommendation(
                    id="travel-zabljak-02",
                    title="Žabljak i Durmitor",
                    category="planina",
                    short_description="Planinski vazduh, jezera i staze za aktivan vikend.",
                    location="Žabljak, Crna Gora",
                    estimated_price="srednji budžet",
                    date_or_duration="2-4 dana",
                    reason="Odličan izbor za prirodu, planinu i reset od grada.",
                    image_url="https://example.com/images/askhype-zabljak.jpg",
                    source_url="https://example.com/travel/zabljak",
                ),
                Recommendation(
                    id="travel-budva-03",
                    title="Budva",
                    category="more",
                    short_description="Kombinacija plaža, starog grada i noćnog života na obali.",
                    location="Budva, Crna Gora",
                    estimated_price="srednji do viši budžet",
                    date_or_duration="2-3 dana",
                    reason="Dobra opcija ako želiš putovanje koje lako pređe iz dnevnog odmora u večernji izlazak.",
                    image_url="https://example.com/images/askhype-budva.jpg",
                    source_url="https://example.com/travel/budva",
                ),
            ],
            [
                "Napravi vikend itinerar",
                "Prikaži jeftinije opcije",
                "Dodaj predloge za Hrvatsku",
            ],
        )

    def _food_response(
        self, request: ChatRequest
    ) -> tuple[str, list[Recommendation], list[str]]:
        location = request.location
        interests = self._interest_phrase(request)
        return (
            f"Za hranu u mestu {location}, predložio bih miks tradicionalnog, modernog i lokalnog skrivenog mesta"
            f"{interests}.",
            [
                Recommendation(
                    id="food-traditional-01",
                    title="Tradicionalni balkanski restoran",
                    category="restoran",
                    short_description="Roštilj, domaća jela i atmosfera koja odgovara dužem ručku.",
                    location=location,
                    estimated_price="1.500-3.000 RSD po osobi",
                    date_or_duration="ručak ili večera",
                    reason="Siguran izbor ako želiš poznate ukuse i pun sto za društvo.",
                    image_url="https://example.com/images/askhype-traditional-food.jpg",
                    source_url="https://example.com/food/traditional",
                ),
                Recommendation(
                    id="food-modern-02",
                    title="Moderni restoran sa lokalnim namirnicama",
                    category="restoran",
                    short_description="Savremen meni sa balkanskim sastojcima i pažljivijom prezentacijom.",
                    location=location,
                    estimated_price="2.500-5.000 RSD po osobi",
                    date_or_duration="večera",
                    reason="Dobar predlog za sastanak, rođendan ili mirniji izlazak.",
                    image_url="https://example.com/images/askhype-modern-food.jpg",
                    source_url="https://example.com/food/modern",
                ),
                Recommendation(
                    id="food-hidden-03",
                    title="Lokalno skriveno mesto",
                    category="hrana",
                    short_description="Malo mesto sa kratkim menijem, brzom uslugom i jakim lokalnim karakterom.",
                    location=location,
                    estimated_price="800-1.800 RSD po osobi",
                    date_or_duration="45-75 minuta",
                    reason="Vredi kada želiš nešto autentično, ne previše formalno.",
                    image_url="https://example.com/images/askhype-hidden-food.jpg",
                    source_url="https://example.com/food/hidden",
                ),
            ],
            [
                "Pronađi opcije za vegetarijance",
                "Predloži mesta za kasnu večeru",
                "Složi rutu za hranu i šetnju",
            ],
        )

    def _fallback_response(
        self, request: ChatRequest
    ) -> tuple[str, list[Recommendation], list[str]]:
        location = request.location
        interests = self._interest_phrase(request)
        return (
            f"AskHype može da pomogne oko izlazaka, hrane, događaja i putovanja po Balkanu. Za {location},"
            f" evo tri dobra početna pravca{interests}.",
            [
                Recommendation(
                    id="fallback-events-01",
                    title="Aktuelni događaji u gradu",
                    category="događaji",
                    short_description="Pregled koncerata, izložbi i manjih gradskih programa.",
                    location=location,
                    estimated_price="različito",
                    date_or_duration="danas do vikenda",
                    reason="Najbrže otkriva šta se stvarno dešava oko tebe.",
                    image_url="https://example.com/images/askhype-events.jpg",
                    source_url="https://example.com/events",
                ),
                Recommendation(
                    id="fallback-food-02",
                    title="Hrana sa lokalnim karakterom",
                    category="hrana",
                    short_description="Mesta koja kombinuju poznate balkanske ukuse i dobru lokaciju.",
                    location=location,
                    estimated_price="srednji budžet",
                    date_or_duration="ručak ili večera",
                    reason="Dobar prvi korak kada nemaš precizan plan.",
                    image_url="https://example.com/images/askhype-food.jpg",
                    source_url="https://example.com/food",
                ),
                Recommendation(
                    id="fallback-travel-03",
                    title="Kratko balkansko putovanje",
                    category="putovanje",
                    short_description="Ideja za vikend beg u regionu, od mora do planine.",
                    location="Balkan",
                    estimated_price="zavisi od rute",
                    date_or_duration="2-3 dana",
                    reason="Korisno kada želiš promenu scene bez velikog planiranja.",
                    image_url="https://example.com/images/askhype-balkan-trip.jpg",
                    source_url="https://example.com/travel",
                ),
            ],
            [
                "Pitaju me za izlazak večeras",
                "Pitaju me za vikend putovanje",
                "Pitaju me za restoran u blizini",
            ],
        )

    def _sources(self) -> list[SourceReference]:
        return [
            SourceReference(
                title="AskHype mock katalog događaja",
                url="https://example.com/askhype/mock-events",
                last_verified=MOCK_LAST_VERIFIED,
            ),
            SourceReference(
                title="AskHype mock vodič kroz Balkan",
                url="https://example.com/askhype/mock-balkan-guide",
                last_verified=MOCK_LAST_VERIFIED,
            ),
        ]

    def _conversation_id(self, request: ChatRequest) -> str:
        key = "|".join(
            [
                request.message,
                request.location,
                request.language,
                ",".join(request.interests),
            ]
        )
        return f"conv_{uuid5(NAMESPACE_URL, key)}"

    def _interest_phrase(self, request: ChatRequest) -> str:
        if not request.interests:
            return ""
        return f", posebno za interesovanja: {', '.join(request.interests)}"

    def _has_any(self, value: str, keywords: list[str]) -> bool:
        return any(keyword in value for keyword in keywords)
