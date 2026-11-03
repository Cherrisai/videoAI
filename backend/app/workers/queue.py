import redis
from rq import Queue
from app.core.config import get_settings

connection = redis.from_url(get_settings().redis_url)
video_queue = Queue("videos", connection=connection, default_timeout=1800)
