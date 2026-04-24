from datetime import datetime
from typing import Any, Optional

import motor.motor_asyncio

from config import MONGO_URI, DB_NAME


class Database:
    def __init__(self, uri: str, db_name: str):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self._db = self._client[db_name]
        self.users = self._db["users"]
        self.chats = self._db["chats"]
        self.settings = self._db["settings"]

    async def add_user(self, user_id: int, username: Optional[str] = None,
                       first_name: Optional[str] = None) -> None:
        await self.users.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "username": username,
                    "first_name": first_name,
                },
                "$setOnInsert": {"joined_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def is_user(self, user_id: int) -> bool:
        return await self.users.find_one({"_id": user_id}) is not None

    async def total_users(self) -> int:
        return await self.users.count_documents({})

    async def all_users(self):
        async for u in self.users.find({}, {"_id": 1}):
            yield u["_id"]

    async def remove_user(self, user_id: int) -> None:
        await self.users.delete_one({"_id": user_id})

    async def add_chat(self, chat_id: int, title: Optional[str] = None,
                       username: Optional[str] = None) -> None:
        await self.chats.update_one(
            {"_id": chat_id},
            {
                "$set": {"title": title, "username": username},
                "$setOnInsert": {"added_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def total_chats(self) -> int:
        return await self.chats.count_documents({})

    async def all_chats(self):
        async for c in self.chats.find({}):
            yield c

    async def remove_chat(self, chat_id: int) -> None:
        await self.chats.delete_one({"_id": chat_id})

    async def get_setting(self, key: str, default: Any = None) -> Any:
        doc = await self.settings.find_one({"_id": key})
        return doc["value"] if doc else default

    async def set_setting(self, key: str, value: Any) -> None:
        await self.settings.update_one(
            {"_id": key},
            {"$set": {"value": value}},
            upsert=True,
        )

    async def get_chat_setting(self, chat_id: int, key: str, default: Any = None) -> Any:
        doc = await self.settings.find_one({"_id": f"chat:{chat_id}:{key}"})
        return doc["value"] if doc else default

    async def set_chat_setting(self, chat_id: int, key: str, value: Any) -> None:
        await self.settings.update_one(
            {"_id": f"chat:{chat_id}:{key}"},
            {"$set": {"value": value}},
            upsert=True,
        )

    async def increment_counter(self, key: str, by: int = 1) -> int:
        doc = await self.settings.find_one_and_update(
            {"_id": f"counter:{key}"},
            {"$inc": {"value": by}},
            upsert=True,
            return_document=True,
        )
        return int((doc or {}).get("value", by))

    async def get_counter(self, key: str) -> int:
        doc = await self.settings.find_one({"_id": f"counter:{key}"})
        return int((doc or {}).get("value", 0))


db = Database(MONGO_URI, DB_NAME)
