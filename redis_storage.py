from aiogram.fsm.storage.redis import RedisStorage
import redis.asyncio as redis
import config

def get_redis_storage():
    r = redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        password=config.REDIS_PASSWORD,
        decode_responses=True
    )
    return RedisStorage(redis=r)
