from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME


class Database:
    def __init__(self, uri: str, db_name: str):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[db_name]
        self.users = self.db["users"]
        self.sessions = self.db["sessions"]

    # ---------------- USERS ----------------
    async def add_user(self, user_id: int, username: str | None = None):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"username": username}},
            upsert=True,
        )

    async def get_user(self, user_id: int):
        return await self.users.find_one({"_id": user_id})

    async def total_users(self) -> int:
        return await self.users.count_documents({})

    async def all_users(self):
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


db = Database(MONGO_URI, DB_NAME)
