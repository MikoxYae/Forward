from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URI, DB_NAME


class Database:
    def __init__(self, uri: str, db_name: str):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[db_name]
        self.users = self.db["users"]
        self.sessions = self.db["sessions"]
        self.chats = self.db["chats"]
        self.settings = self.db["settings"]
        self.promos = self.db["promos"]

    # ---------------- USERS ----------------
    async def add_user(self, user_id: int, username: str | None = None,
                       first_name: str | None = None):
        await self.users.update_one(
            {"_id": user_id},
            {
                "$set": {"username": username, "first_name": first_name},
                "$setOnInsert": {"joined_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def get_user(self, user_id: int):
        return await self.users.find_one({"_id": user_id})

    async def remove_user(self, user_id: int):
        await self.users.delete_one({"_id": user_id})

    async def total_users(self) -> int:
        return await self.users.count_documents({})

    def all_users(self):
        return self.users.find({})

    # ---------------- SESSIONS (user MTProto sessions) ----------------
    async def save_session(self, user_id: int, session_string: str):
        await self.sessions.update_one(
            {"_id": user_id},
            {"$set": {"session": session_string}},
            upsert=True,
        )

    async def get_session(self, user_id: int) -> str | None:
        doc = await self.sessions.find_one({"_id": user_id})
        return doc.get("session") if doc else None

    async def delete_session(self, user_id: int):
        await self.sessions.delete_one({"_id": user_id})

    # ---------------- PER-USER SETTINGS (source / destination) ----------------
    async def set_user_setting(self, user_id: int, key: str, value):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {f"settings.{key}": value}},
            upsert=True,
        )

    async def get_user_setting(self, user_id: int, key: str):
        doc = await self.users.find_one({"_id": user_id})
        if not doc:
            return None
        return (doc.get("settings") or {}).get(key)

    async def clear_user_setting(self, user_id: int, key: str):
        await self.users.update_one(
            {"_id": user_id},
            {"$unset": {f"settings.{key}": ""}},
        )

    # ---------------- CHATS (where bot has seen join requests) ----------------
    async def add_chat(self, chat_id: int, title: str | None = None,
                       username: str | None = None):
        await self.chats.update_one(
            {"_id": chat_id},
            {
                "$set": {"title": title, "username": username},
                "$setOnInsert": {"added_at": datetime.utcnow()},
            },
            upsert=True,
        )

    async def remove_chat(self, chat_id: int):
        await self.chats.delete_one({"_id": chat_id})

    async def total_chats(self) -> int:
        return await self.chats.count_documents({})

    def all_chats(self):
        return self.chats.find({})

    # ---------------- PER-CHAT SETTINGS (welcome) ----------------
    async def set_chat_setting(self, chat_id: int, key: str, value: Any):
        await self.settings.update_one(
            {"_id": f"chat:{chat_id}:{key}"},
            {"$set": {"value": value}},
            upsert=True,
        )

    async def get_chat_setting(self, chat_id: int, key: str, default: Any = None) -> Any:
        doc = await self.settings.find_one({"_id": f"chat:{chat_id}:{key}"})
        return doc["value"] if doc else default

    # ---------------- COUNTERS ----------------
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

    # ---------------- PROMOS ----------------
    async def _next_promo_id(self) -> int:
        return await self.increment_counter("promo_seq", by=1)

    async def add_promo(self, owner_id: int, target_chat,
                        source_chat_id: int, source_msg_id: int,
                        interval_minutes: int = 20,
                        content: dict | None = None) -> int:
        promo_id = await self._next_promo_id()
        await self.promos.insert_one({
            "_id": promo_id,
            "owner_id": owner_id,
            "target_chat": target_chat,
            "source_chat_id": source_chat_id,
            "source_msg_id": source_msg_id,
            "interval_minutes": int(interval_minutes),
            "enabled": True,
            "last_post_id": None,
            "last_post_at": None,
            "content": content,
            "created_at": datetime.utcnow(),
        })
        return promo_id

    async def get_promo(self, promo_id: int):
        return await self.promos.find_one({"_id": int(promo_id)})

    async def update_promo(self, promo_id: int, **fields):
        if not fields:
            return
        await self.promos.update_one(
            {"_id": int(promo_id)},
            {"$set": fields},
        )

    async def delete_promo(self, promo_id: int):
        await self.promos.delete_one({"_id": int(promo_id)})

    def all_promos(self):
        return self.promos.find({})

    def enabled_promos(self):
        return self.promos.find({"enabled": True})

    def user_promos(self, owner_id: int):
        return self.promos.find({"owner_id": int(owner_id)})

    async def count_user_promos(self, owner_id: int) -> int:
        return await self.promos.count_documents({"owner_id": int(owner_id)})



    # ---------------- RESUME (batch progress) ----------------
    async def save_resume(self, user_id: int, src: str, dest: str,
                          start_id: int, end_id: int, last_id: int):
        await self.settings.update_one(
            {"_id": f"resume:{user_id}"},
            {"$set": {
                "src": src, "dest": dest,
                "start_id": start_id, "end_id": end_id,
                "last_id": last_id,
            }},
            upsert=True,
        )

    async def get_resume(self, user_id: int):
        doc = await self.settings.find_one({"_id": f"resume:{user_id}"})
        return doc if doc else None

    async def clear_resume(self, user_id: int):
        await self.settings.delete_one({"_id": f"resume:{user_id}"})

db = Database(MONGO_URI, DB_NAME)
