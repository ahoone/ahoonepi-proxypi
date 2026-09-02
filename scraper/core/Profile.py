import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from contract.schemas.architecture import ProfileModel
from contract.schemas.new_instance import NewInstanceRequest

from scraper.core.DatabaseHandler import DatabaseHandler
from scraper.core.models.DatabaseHandler import ProfileRecord

SCRAPER_FIRST_NAMES = (
    "Noah",
    "Emma",
    "Liam",
    "Olivia",
    "Lucas",
    "Sophia",
    "Ethan",
    "Mia",
    "Leo",
    "Ava",
    "Jack",
    "Chloe",
    "Henry",
    "Lily",
    "Owen",
    "Zoe",
    "Felix",
    "Grace",
    "Max",
    "Ella",
    "Oscar",
    "Ruby",
    "Hugo",
    "Nora",
    "Theo",
    "Alice",
    "Arthur",
    "Clara",
    "Samuel",
    "Lucy",
    "Daniel",
    "Ivy",
    "Julian",
    "Hazel",
    "Nathan",
    "Rose",
    "Eli",
    "Stella",
    "Isaac",
    "Maya",
    "Gabriel",
    "Jade",
    "Adam",
    "Violet",
    "Caleb",
    "Iris",
    "Simon",
    "Luna",
    "Xavier",
    "Nina",
    "Oliver",
    "Eva",
    "Benjamin",
    "Julia",
    "Thomas",
    "Sadie",
    "David",
    "Molly",
    "Ryan",
    "Bella",
    "Alex",
    "Sophie",
    "Finn",
    "Elena",
    "Dylan",
    "Layla",
    "Aaron",
    "Naomi",
    "Victor",
    "Piper",
    "Jasper",
    "Aria",
    "Miles",
    "Cora",
    "Rowan",
    "Leah",
    "Sebastian",
    "Daphne",
    "Wesley",
    "Freya",
    "Connor",
    "Paige",
    "Evan",
    "Tessa",
    "Damian",
    "Holly",
    "Parker",
    "Skye",
    "Adrian",
    "Brooke",
    "Colin",
    "June",
    "Vincent",
    "Willa",
    "Tristan",
    "Faye",
    "Jonah",
    "Quinn",
    "Blake",
    "Avery",
)
SCRAPER_ADJECTIVES = (
    "Curious",
    "Sleepy",
    "Sparkling",
    "Mysterious",
    "Tiny",
    "Gigantic",
    "Sneaky",
    "Cheerful",
    "Grumpy",
    "Fearless",
    "Fluffy",
    "Electric",
    "Cosmic",
    "Wobbly",
    "Brilliant",
    "Silly",
    "Swift",
    "Moody",
    "Radiant",
    "Legendary",
    "Noisy",
    "Quiet",
    "Lucky",
    "Dramatic",
    "Epic",
    "Chaotic",
    "Noble",
    "Dazzling",
    "Frozen",
    "Fiery",
    "Golden",
    "Invisible",
    "Playful",
    "Stubborn",
    "Magical",
    "Reckless",
    "Clever",
    "Dreamy",
    "Jazzy",
    "Funky",
    "Sneezing",
    "Hungry",
    "Bouncy",
    "Glorious",
    "Spooky",
    "Daring",
    "Shiny",
    "Caffeinated",
    "Whimsical",
    "Wild",
    "Elegant",
    "Peculiar",
    "Fierce",
    "Goofy",
    "Hyperactive",
    "Melodic",
    "Secretive",
    "Thunderous",
    "Velvety",
    "Adventurous",
    "Quirky",
    "Vintage",
    "Galactic",
    "Prickly",
    "Heroic",
    "Fuzzy",
    "Regal",
    "Neon",
    "Wandering",
    "Lunar",
    "Solar",
    "Rainbow",
    "Turbocharged",
    "Cranky",
    "Sneaky-Beaky",
    "Philosophical",
    "Unstoppable",
    "Tactical",
    "Bewildered",
    "Marshmallowy",
    "Pirate-like",
    "Viking",
    "Baffling",
    "Determined",
    "Rogue",
    "Chill",
    "Boisterous",
    "Enchanted",
    "Mischievous",
    "Bewitching",
    "Absurd",
    "Glittering",
    "Squeaky",
    "Thunderstruck",
    "Majestic",
    "Witty",
    "Resilient",
    "Eccentric",
    "Zany",
    "Supreme",
)

logger = logging.getLogger(__name__)


@dataclass
class Profile:
    uuid: UUID
    name: str
    created_at: datetime
    user_data_dir: Path
    is_temporary: bool = False

    @classmethod
    async def create(cls, request: NewInstanceRequest) -> "Profile":
        if not request.profile_uuid:
            instance = await cls.__create_new_profile(request)
            # await instance.__save_profile()
        else:
            profile_record: ProfileRecord = await DatabaseHandler.get_profile_from_uuid(
                request.profile_uuid
            )
            instance = cls.from_record(profile_record)
        return instance

    @classmethod
    async def __create_new_profile(cls, request: NewInstanceRequest) -> "Profile":
        uuid = uuid4()
        user_data_dir = Path(
            f"/tmp/chrome-profile-{uuid}"
            if request.is_temporary
            else f"/data/profiles/chrome-profile-{uuid}"
        )
        name = (
            request.profile_name
            if request.profile_name
            else f"{random.choice(SCRAPER_ADJECTIVES)} {random.choice(SCRAPER_FIRST_NAMES)}"
        )
        instance = cls(
            uuid=uuid,
            name=name,
            created_at=datetime.now(UTC),
            user_data_dir=user_data_dir,
            is_temporary=request.is_temporary,
        )
        return instance

    async def __save_profile(self) -> None:
        if self.is_temporary:
            raise RuntimeError(f"Cannot save a temporary profile: {self.uuid}")
        await DatabaseHandler.insert_profile_record(self.to_record())

    def to_model(self) -> ProfileModel:
        return ProfileModel(
            uuid=self.uuid,
            name=self.name,
            created_at=self.created_at,
            user_data_dir=self.user_data_dir,
            is_temporary=self.is_temporary,
        )

    @classmethod
    def from_record(cls, profile_record: ProfileRecord) -> "Profile":
        instance = cls(
            uuid=profile_record.uuid,
            name=profile_record.name,
            created_at=profile_record.created_at,
            user_data_dir=profile_record.user_data_dir,
        )
        return instance

    def to_record(self) -> ProfileRecord:
        return ProfileRecord(
            uuid=self.uuid,
            name=self.name,
            created_at=self.created_at,
            user_data_dir=self.user_data_dir,
        )

    async def close(self) -> None:
        if not self.is_temporary:
            await self.__save_profile()
