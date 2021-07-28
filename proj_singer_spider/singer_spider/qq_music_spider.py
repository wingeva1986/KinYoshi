# coding=utf-8
import argparse
from datetime import datetime
import multiprocessing
import os
import json
import queue
import re
import sys
import threading
import time
import logging
import pymongo
import requests
from pymongo import InsertOne


sys.path.append('.')
sys.path.append('..')
from util.MyThread import MyThread
from util.CommonUtils import bulk_insert, RedisCache
from util.CommonUtils import send_singer_spider_message, quiet_threads, remove_special_symbols, save_picture

logger = logging.getLogger(__name__)

SERVER = '192.168.2.5'
PORT = 27017
redis_server = '127.0.0.1'
redis_port = 6379
redis_db = 0
redis_cache = RedisCache(redis_server, redis_port, redis_db)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36'}
area_dic = {
    '200': '内地', '2': '港台', '5': '欧美',
    '4': '日本', '3': '韩国', '6': '其他'
}
genre_dic = {
    '1': '流行', '6': '嘻哈', '2': '摇滚',
    '4': '电子', '3': '民谣', '8': 'R&B',
    '10': '民歌', '9': '轻音乐', '5': '爵士',
    '14': '古典', '25': '乡村', '20': '蓝调'
}
sex_dic = {
    '0': '男', '1': '女', '2': '组合'
}
zm_list = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V',
           'W', 'X', 'Y', 'Z', '#']
index_dic = {'-100': '热门'}
for i in range(0, 27):
    index_dic[str(i + 1)] = zm_list[i]


def insert_item_to_db(db_handle, singer_item):
    try:
        db_handle.insert_one(singer_item)
        logger.info('%s, %s', singer_item['singer_id'], singer_item['singer_name'])
    except Exception as e:
        logger.warning(f'insert item error {e}')


def find_item(db_handle, singer_item):
    try:
        result = redis_cache.get_redis_cache(singer_item['singer_id'])
        if result:
            logger.info(f'get {singer_item["singer_id"]} in cache')
            return result
        else:
            singer_info = db_handle.find_one(
                {'singer_id': singer_item['singer_id'], 'singer_mid': singer_item['singer_mid']}
            )
            redis_cache.set_redis_cache(singer_item['singer_id'], singer_info)
            logger.info(f'save {singer_item["singer_id"]} to cache')
            return singer_info
    except Exception as e:
        logger.warning(f'find error {e}')
        return {}


def update_singer_field(db_handle, item, field, **kwargs):
    try:
        db_handle.update_one(
            {'id': item['id'], 'name': item['name']},
            {'$set': {field: item[field]}}
        )
        logger.info(f'update {field} success')
    except Exception as e:
        logger.warning('update error %s', e)


def get_url_list(sex_dict, area_dict, genre_dict, index_dict):
    url_list = []
    try:
        base_url = 'http://localhost:3200/getSingerList?area={area}&sex={sex}&index={index}&genre={genre}'
        for sex in sex_dict.keys():
            for area in area_dict.keys():
                for genre in genre_dict.keys():
                    for index in index_dict.keys():
                        url = base_url.format(area=area, sex=sex, index=index, genre=genre)
                        url_list.append(url)
    except Exception as e:
        logger.warning(f'get url list error {e}')
    return url_list


def get_singer_info(singer_mid):
    baseurl = 'http://localhost:3200/getSingerDesc?singermid={singermid}'
    url = baseurl.format(singermid=singer_mid)
    try:
        response = requests.get(url, headers=headers, timeout=120)
        data = json.loads(response.text)
        detail = data['response'] if 'response' in data.keys() else ''
        new_detail = ' '.join(re.findall(r'<\!\[CDATA\[(.*?)\]\]>', detail))
        return new_detail
    except Exception as e:
        logger.warning(e)
        return ''


def singer_spider(url, db_handle, picture_path, **kwargs):
    area = kwargs.get('area', '')
    index = kwargs.get('index', '')
    sex = kwargs.get('sex', '')
    genre = kwargs.get('genre', '')
    all_spider_mode = kwargs.get('all_spider_mode', False)

    url = url + '&page={page}'
    for page in range(1, 1000):
        try:
            api_url = url.format(page=page)
            logger.info(f'Scrapying {api_url}')
            response = requests.get(api_url, headers=headers, timeout=120)
            data = json.loads(response.text)
            if data['status'] == 200:
                try:
                    singer_list = data['response']['singerList']['data']['singerlist']
                    if singer_list:
                        insert_list = []
                        for sl in singer_list:
                            singer_item = dict()
                            singer_item['singer_id'] = str(sl['singer_id']) if 'singer_id' in sl.keys() else ''
                            singer_item['singer_mid'] = str(sl['singer_mid']) if 'singer_mid' in sl.keys() else ''
                            singer_item['index'] = index
                            singer_item['singer_name'] = str(sl['singer_name']) if 'singer_name' in sl.keys() else ''
                            singer_item['sex'] = sex
                            singer_item['area'] = area
                            singer_item['genre'] = genre
                            singer_item['country'] = str(sl['country']) if 'country' in sl.keys() else ''
                            singer_item['scrapy_date'] = str(int(time.time()))
                            singer_item['scrapy_date_str'] = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
                            singer_item['uploaded_pic'] = False
                            db_item = find_item(db_handle, singer_item)
                            if not db_item:
                                name = remove_special_symbols(sl['singer_name']).strip()
                                pic_url = sl['singer_pic'] if 'singer_pic' in sl.keys() else ''
                                pic_name = '.'.join(
                                    [name, str(sl['singer_id']), pic_url.split('/')[-1]]) if pic_url else ''
                                singer_pic_path = os.path.join(picture_path, pic_name)

                                result = save_picture(pic_url, singer_pic_path)
                                singer_item['singer_pic'] = singer_pic_path if result else ''
                                singer_item['detail'] = get_singer_info(singer_item['singer_mid'])

                                insert_list.append(singer_item)
                                # insert_item_to_db(db_handle, singer_item)
                            else:
                                if all_spider_mode:
                                    for key, value in singer_item.items():
                                        if singer_item[key] != db_item[key]:
                                            update_singer_field(db_handle, db_item, key)
                                else:
                                    logger.info(f'{singer_item["singer_name"]} is in db')
                            time.sleep(0.5)
                        if insert_list:
                            bulk_insert(db_handle, insert_list)
                    else:
                        logger.info('no data, break')
                        break
                except Exception as ee:
                    logger.warning('get data error %s', ee)
        except Exception as e:
            logger.warning('get singer list error %s', e)
            logger.warning('warning url -> %s', url)
            break


def spider_process(picture_path, queueLock, workQueue, db_handle, all_spider_mode):
    if not workQueue.empty():
        url = workQueue.get()
        try:
            area = area_dic[re.findall(r'area=(\d+)&', url)[0]]
            sex = sex_dic[re.findall(r'sex=(\d+)&', url)[0]]
            genre = genre_dic[re.findall(r'genre=(\d+)', url)[0]]
            index = index_dic[re.findall(r'index=([\d-]+)&', url)[0]]

            singer_spider(url, db_handle, picture_path, area=area, sex=sex, genre=genre, index=index,
                          all_spider_mode=all_spider_mode)
        except Exception as e:
            logger.warning(e)


def start_spider_stasks(db_handle, **kwargs):
    all_spider_mode = kwargs.get('all_spider_mode', False)
    picture_path = kwargs.get('picture_path', '')
    tasks = kwargs.get('tasks', 16)

    threads = []
    queueLock = threading.Lock()
    QUEUE_SIZE = 50
    workQueue = queue.Queue(QUEUE_SIZE)

    for task in range(1, tasks):
        thread = MyThread(func=spider_process,
                          args=(picture_path, queueLock, workQueue, db_handle, all_spider_mode),
                          counter=MyThread.FORVER_LOOP_COUNT,
                          name='Spider-' + str(task),
                          sleep=10)
        thread.start()
        # 添加线程到线程列表
        threads.append(thread)

    try:
        url_list = get_url_list(sex_dic, area_dic, genre_dic, index_dic)
        send_singer_spider_message(url_list, workQueue)
        quiet_threads(threads)
    except KeyboardInterrupt:
        logging.info("you interrupt the spider,will stop")
        quiet_threads(threads)

    logger.info("Exiting Main Thread")


def main(args):
    client = pymongo.MongoClient(host=SERVER, port=PORT)
    db = client.klok_media_db
    db_handle = db.qq_music_singer_info
    hour = int(args.hour)
    minute = int(args.minute)
    all_spider_mode = args.all_spider
    picture_path = args.picture_path
    if not picture_path:
        # picture_path = os.path.join(os.path.realpath('.'), 'picture')
        picture_path = 'E:\\singer_picture'
    if not os.path.exists(picture_path):
        os.makedirs(picture_path)

    while True:
        now = datetime.now()
        if now.hour == hour and now.minute >= minute:
            start_spider_stasks(db_handle, picture_path=picture_path, all_spider_mode=all_spider_mode)
        logger.info(f'{now} wait for time')
        time.sleep(60)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    parser = argparse.ArgumentParser(description=" --help")
    parser.add_argument('-a', '--all_spider', default=False)
    parser.add_argument('-pic_path', '--picture_path', default='')
    parser.add_argument('-hour', '--hour', default='00')
    parser.add_argument('-minute', '--minute', default='00')
    args = parser.parse_args()
    main(args)

'''
python qq_music_spider.py -h 13 -m 00
'''