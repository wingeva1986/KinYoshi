# coding=utf-8
import argparse
from datetime import datetime
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
from util.CommonUtils import quiet_threads, send_singer_spider_message, remove_special_symbols, save_picture

logger = logging.getLogger(__name__)

SERVER = '192.168.2.5'
PORT = 27017
redis_server = '127.0.0.1'
redis_port = 6379
redis_db = 0
redis_cache = RedisCache(redis_server, redis_port, redis_db)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36'}
type_dic = {
    '1': '男歌手', '2': '女歌手', '3': '乐队'
}
area_dic = {
    '7': '华语', '96': '欧美', '8': '日本', '16': '韩国', '0': '其他'
}
initial_list = ['-1', '0', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', '0', 'P', 'Q', 'R',
                'S', 'T', 'U',
                'V',
                'W', 'X', 'Y', 'Z']


def get_initial(initial):
    if initial == '-1':
        return '热门'
    elif initial == '0':
        return '#'
    else:
        return initial


def get_sex(string):
    if '男' in string:
        return '男'
    elif '女' in string:
        return '女'
    else:
        return string


def get_url_list(type_dict, area_dict, initials):
    url_list = []
    try:
        url = 'http://localhost:3000/artist/list?type={type}&area={area}&initial={index}'
        for i in type_dict.keys():
            for j in area_dict.keys():
                for k in initials:
                    url_list.append(url.format(type=i, area=j, index=k))
    except Exception as e:
        logger.warning(f'get url list error {e}')
    return url_list


def insert_item_to_db(db_handle, singer_item):
    try:
        db_handle.insert_one(singer_item)
        logger.info('insert %s to db success', singer_item['name'])
    except Exception as e:
        logger.warning('insert error %s', e)


def find_item(db_handle, singer_item):
    try:
        result = redis_cache.get_redis_cache(singer_item['id'])
        if result:
            logger.info(f'get {singer_item["id"]} in cache')
            return result
        else:
            singer_info = db_handle.find_one({'id': singer_item['id']})
            redis_cache.set_redis_cache(singer_item['id'], singer_info)
            logger.info(f'save {singer_item["id"]} to cache')
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


def get_singer_detail(id):
    detail = ''
    url = 'http://localhost:3000/artist/desc?id={id}'.format(id=id)
    try:
        response = requests.get(url, headers=headers, timeout=120)
        data = json.loads(response.text)

        if data['code'] == 200:
            detail = data['briefDesc'] if 'briefDesc' in data.keys() else ''
    except Exception as e:
        logger.warning(f'get detail error{e}')
    return detail


def singer_spider(url, db_handle, picture_path, **kwargs):
    singer_type = kwargs.get('singer_type', '')
    area = kwargs.get('area', '')
    index = kwargs.get('index', '')
    all_spider_mode = kwargs.get('all_spider_mode', False)

    for offset in range(0, 990, 30):
        try:
            api_url = url.format(offset=offset)
            logger.info('Scrapy url %s', api_url)
            response = requests.get(api_url, headers=headers, timeout=120)
            data = json.loads(response.text)
            if data['code'] == 200:
                more = data['more']
                if not more:
                    break
                try:
                    artists_list = data['artists']
                    if artists_list:
                        insert_list = []
                        for al in artists_list:
                            singer_item = al
                            singer_item['genre'] = '[1]流行'
                            singer_item['sex'] = get_sex(singer_type)
                            singer_item['area'] = area
                            singer_item['index'] = index
                            singer_item['scrapy_date'] = str(int(time.time()))
                            singer_item['scrapy_date_str'] = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
                            singer_item['uploaded_pic'] = False

                            db_item = find_item(db_handle, singer_item)
                            if not db_item:
                                name = remove_special_symbols(al['name']).strip()
                                img1v1_name = '.'.join([name, str(al['id']), al['img1v1Url'].split('/')[-1]])
                                pic_name = '.'.join([name, str(al['id']), al['picUrl'].split('/')[-1]])
                                img1v1_path = os.path.join(picture_path, img1v1_name)
                                pic_path = os.path.join(picture_path, pic_name)

                                img1v1_result = save_picture(al['img1v1Url'], img1v1_path)
                                singer_item['img1v1_path'] = img1v1_path if img1v1_result else ''
                                pic_result = save_picture(al['picUrl'], pic_path)
                                singer_item['pic_path'] = pic_path if pic_result else ''
                                singer_item['detail'] = get_singer_detail(al['id'])

                                logger.info(f"{name}-{singer_item['id']}")
                                insert_list.append(singer_item)
                                # insert_item_to_db(db_handle, singer_item)
                            else:
                                if all_spider_mode:
                                    for key, value in singer_item.items():
                                        if singer_item[key] != db_item[key]:
                                            update_singer_field(db_handle, db_item, key)
                                else:
                                    logger.info(f'{singer_item["name"]} is in db')
                            time.sleep(0.5)
                        if insert_list:
                            bulk_insert(db_handle, insert_list)
                except Exception as e:
                    logger.warning('get data error %s', e)
        except Exception as e:
            logger.warning('get singer info error %s', e)


def spider_process(picture_path, queueLock, workQueue, db_handle, all_spider_mode):
    if not workQueue.empty():
        url = workQueue.get()
        url = url + '&offset={offset}'
        try:
            singer_type = type_dic[re.findall(r'type=(\d+)&', url)[0]]
            area = area_dic[re.findall(r'area=(\d+)&', url)[0]]
            index = get_initial(re.findall(r'initial=([\d\w-]+)&', url)[0])

            singer_spider(url, db_handle, picture_path, area=area, sex=singer_type, index=index,
                          all_spider_mode=all_spider_mode)
        except Exception as e:
            logger.warning(e)


def start_spider_stasks(db_handle, **kwargs):
    all_spider_mode = kwargs.get('all_spider_mode', False)
    picture_path = kwargs.get('picture_path', '')
    tasks = kwargs.get('tasks', 16)

    threads = []
    queueLock = threading.Lock()
    QUEUE_SIZE = 30
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
        url_list = get_url_list(type_dic, area_dic, initial_list)
        send_singer_spider_message(url_list, workQueue)
        quiet_threads(threads)
    except KeyboardInterrupt:
        logging.info("you interrupt the spider,will stop")
        quiet_threads(threads)

    logger.info("Exiting Main Thread")


def main(args):
    client = pymongo.MongoClient(host=SERVER, port=PORT)
    db = client.klok_media_db
    db_handle = db.cloud_music_singer_info
    db_handle.create_index([
        ("id", pymongo.ASCENDING),
        ("name", pymongo.ASCENDING),
    ], unique=True)
    hour = int(args.hour)
    minute = int(args.minute)
    all_spider_mode = args.all_spider
    picture_path = args.picture_path
    if not picture_path:
        # picture_path = os.path.join(os.path.realpath('.'), 'picture')
        picture_path = 'E:\cm_picture'
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
    # 'http://localhost:3000/artist/list?type=1&area=7&initial=-1&offset={offset}'
    parser = argparse.ArgumentParser(description=" --help")
    parser.add_argument('-a', '--all_spider', default=False)
    parser.add_argument('-pic_path', '--picture_path', default='')
    parser.add_argument('-hour', '--hour', default='00')
    parser.add_argument('-minute', '--minute', default='00')
    args = parser.parse_args()
    main(args)
