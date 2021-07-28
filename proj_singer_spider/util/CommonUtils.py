# coding=utf-8
import json
import logging
import os
import time

import redis
import requests
from bson import json_util
from cacheout import Cache

logger = logging.getLogger(__name__)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36'}


def bulk_insert(db_handle, insert_list):
    try:
        db_handle.insert_many(insert_list, ordered=False)
        logger.info('insert success')
    except Exception as e:
        logger.warning(f'insert error {e}')


def remove_special_symbols(name):
    special_symbols = ['\\', '/', ':', '?', '"', '<', '>', '|', '$', '[', ']', '%', '&', '#', '~', '*']
    for symbols in special_symbols:
        name = name.replace(symbols, '')
    return name


def save_picture(url, singer_pic_path):
    result = False
    try:
        if not os.path.exists(singer_pic_path):
            response = requests.get(url, headers=headers, timeout=120)
            with open(singer_pic_path, 'wb') as f:
                f.write(response.content)
                result = True
    except Exception as e:
        logger.warning('save picture error %s', e)
    return result


def send_singer_spider_message(url_list, workQueue):
    count = 0
    url_list_len = len(url_list)
    for url in url_list:
        successed = False
        while not successed:
            if workQueue.full():
                logger.info(f'send_singer_spider_message {url} wait te send ')
                time.sleep(10)
            else:
                workQueue.put(url)
                successed = True
                count += 1
                logger.info('send_movie_download_message %d/%s successed ', count, url_list_len)

    while not workQueue.empty():
        time.sleep(10)
        logger.info('start_spider_task workQueue not empty wait a while ')


def quiet_threads(threads):
    logging.info("wait for to leave Main Thread")

    # 设置线程退出
    for t in threads:
        logger.info('all the message are consumed ,try stop the task %s', t.getName())
        t.set_stop()

    # 等待所有线程完成
    for t in threads:
        logger.info('all the message are consumed ,try join() the task %s', t.getName())
        t.join()


class RedisCache:
    def __init__(self, host, port, db):
        self.redis_pool = redis.ConnectionPool(host=host, port=port)
        self.redis_cache = redis.Redis(connection_pool=self.redis_pool, db=db)

    def set_redis_cache(self, key, obj):
        if not not self.redis_cache:
            cache_str = json_util.dumps(obj)
            self.redis_cache.set(key, cache_str, ex=86400)

    def get_redis_cache(self, key):
        obj = None
        if not not self.redis_cache:
            cache_str = self.redis_cache.get(key)
            if not not cache_str:
                obj = json.loads(cache_str)
        return obj


if __name__ == '__main__':
    redis_cache = RedisCache('127.0.0.1', 6379, 0)
    redis_cache.set_redis_cache('abc', {'1': '2'})
    print(redis_cache.get_redis_cache('abc'))