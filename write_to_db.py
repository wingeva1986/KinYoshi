# coding=utf-8
import json
import os
import platform
import random
import re
import subprocess
import time
import logging
import urllib
import sys
import pandas
import pymongo
import requests
from bson import ObjectId
sys.path.append('.')
sys.path.append('..')
from requests.utils import dict_from_cookiejar

from utils.util_agent import choice_agent

logger = logging.getLogger(__name__)
data_source = '192.168.2.9'
client = pymongo.MongoClient(host=data_source, port=27117)
client.admin.authenticate("svcadmin", "admin#svc2020")
db = client.tp_media_assert_db
key_map = {
    "video_type": "",
    "album_type": "",
    "multi_name": [],
    "name": "",
    "director": "",
    "writer": "",
    "main_actor": [],
    "service_type": [],
    "view_point": "",
    "area": "",
    "language": "",
    "release_date": "",
    "year": "",
    "IMDb_id": "",
    "TMDb_id": "",
    "douban_id": "",
    "details": "",
    "poster": "",
    "score": "",
    "page_url": "",
    "seasons": "1",
    "subtitles": [],
    "is3d": "[0]否",
    "is_end": "",
    "landscape_poster": "",
    "subtitle_languages": "",
    "target_group": "中国",
    "scrapy_date": "",
    "scrapy_date_str": "",
    "seq_num": "",
    "update_seq_num": "",
    "total_seq_num": "",
    "download_url": {
        "name": "",
        "url": "",
        "episode_name": ""
    },
    "download_state": {
        "source": "",
        "status": "2",
        "result": "0",
        "time": ""
    }
}


def remove_special_symbols(name):
    special_symbols = ['\\', '/', ':', '?', '"', '<', '>', '|',
                       '$', '[', ']', '%', '&', '#', '~', '*', '(', ')', "'"]
    for symbols in special_symbols:
        name = name.replace(symbols, '')
    return name


def get_info_with_douban(name, video_type, year):
    data = {}
    url = f'http://192.168.2.9:9999/mytmdb/api/v1/douban_with_name?name={name}&video_type={video_type}&year={year}'
    try:
        data = json.loads(requests.get(url).text)['result']
    except Exception as e:
        logger.warning(f'get data error {e}')
    return data


def get_info_for_douban(name, **kwargs):
    douban_id = kwargs.get('douban_id', '')
    year = kwargs.get('year', '')
    video_type = kwargs.get('video_type', '')

    if douban_id:
        url = f'http://192.168.2.9:9999/mytmdb/api/v1/douban/{douban_id}'
        data = json.loads(requests.get(url, timeout=120).text)['result']
    elif name and year and video_type:
        data = get_info_with_douban(name, video_type, year)
    else:
        data = {}
    return data


def generate_media_assets(name, **kwargs):
    new_res = {}
    douban_id = kwargs.get('douban_id', '')
    year = kwargs.get('year', '')
    video_type = kwargs.get('video_type', '')
    seq_num = kwargs.get('seq_num', '1')
    season = kwargs.get('season', '1')
    download_url = kwargs.get('download_url', '')
    language = kwargs.get('language', '')
    episode_name = kwargs.get('episode_name', '')
    result = get_info_for_douban(
        name, douban_id=douban_id, year=year, video_type=video_type)

    if result:
        for key in key_map.keys():
            if key in result.keys():
                new_res[key] = result[key]
            else:
                new_res[key] = ''
        new_res['name'] = name
        if language:
            new_res['language'] = language
        score = str(round(random.uniform(5, 7), 1)
                    ) if not result['score'] else result['score']
        new_res['score'] = score
        if not result['season']:
            new_res['seasons'] = season
        else:
            new_res['seasons'] = result['season']
        new_res['total_seq_num'] = ''
        new_res['seq_num'] = new_res['update_seq_num'] = str(seq_num)
        new_res['multi_name'] = result['multilingual_name']
        # new_res['multi_name'] = ''
        new_res['IMDb_id'] = result['IMDb']
        new_res['sort'] = 20
        new_res['scrapy_date'] = str(int(time.time()))
        new_res['scrapy_date_str'] = time.strftime('%Y-%m-%d %H:%M:%S')
        new_res['download_url'] = {
            'name': name,
            'url': download_url,
            'episode_name': ".".join([remove_special_symbols(name), seq_num, "mp4"]) if not episode_name else '.'.join([str(episode_name), 'mp4'])}
        # new_res['download_url'] = {'name': name, 'url': '', 'episode_name': f"{remove_special_symbols(name)}-{seq_num}.mp4"}
        new_res['download_state'] = key_map['download_state']
        new_res['download_state']['time'] = time.strftime('%Y-%m-%d %H:%M:%S')
        # new_res.pop('download_state')
    return new_res


def get_key_value(video_type, album_type, name, year, seasons, seq_num, **kwargs):
    multi_name = kwargs.get('multi_name', [])
    service_type = kwargs.get('service_type', [])
    director = kwargs.get('director', '')
    area = kwargs.get('area', '')
    language = kwargs.get('language', '')
    douban_id = kwargs.get('douban_id', '')
    details = kwargs.get('details', '')
    poster = kwargs.get('poster', '')
    score = kwargs.get('score', '')
    download_url = kwargs.get('download_url', '')

    insert_dic = key_map
    insert_dic['video_type'] = video_type
    insert_dic['album_type'] = album_type
    insert_dic['name'] = name
    insert_dic['multi_name'] = multi_name
    insert_dic['year'] = year
    insert_dic['details'] = details
    insert_dic['seasons'] = seasons
    insert_dic['seq_num'] = insert_dic['update_seq_num'] = insert_dic['total_seq_num'] = seq_num
    insert_dic['director'] = director
    insert_dic['area'] = area
    insert_dic['language'] = language
    insert_dic['poster'] = poster
    insert_dic['service_type'] = service_type
    insert_dic['view_point'] = '|'.join(service_type)
    insert_dic['douban_id'] = douban_id
    insert_dic['score'] = str(
        round(random.uniform(5, 7), 1)) if not score else score
    insert_dic['scrapy_date'] = str(int(time.time()))
    insert_dic['scrapy_date_str'] = time.strftime('%Y-%m-%d %H:%M:%S')
    seq_sea = "s{season}e{seq}".format(season=seasons, seq=seq_num)
    time_stamp = str(int(time.time() * 1e7)) + str(random.randint(0, 9))
    insert_dic['download_url'] = {'name': name, 'url': download_url,
                                  'episode_name': f'{remove_special_symbols(name)}.{seq_num}.mp4'}
    insert_dic['download_state']['time'] = time.strftime('%Y-%m-%d %H:%M:%S')
    return insert_dic


def insert_to_db(db_handle, item):
    try:
        item['_id'] = ObjectId()
        db_handle.insert_one(item)
        logger.info('insert success')
    except Exception as e:
        logger.warning(f'insert error {e}')


def insert_movie_data(db_handle, name: str, douban_id: str, **kwargs):
    episode_name = kwargs.get('episode_name', '')
    data = generate_media_assets(
        name, douban_id=douban_id, episode_name=episode_name)
    print(data)
    insert_to_db(db_handle, data)


def insert_tv_series(db_handle, name: str, douban_id: str, total_episode: int, **kwargs):
    language = kwargs.get('language', '')
    episode_name = kwargs.get('episode_name', '')
    # download_url = kwargs.get('download_url', '')
    for i in range(1, total_episode + 1):
        seq_num = f'{i}'
        if not episode_name:
            episode_name = f'{name}.{seq_num}'
        # data = key_map
        # data['seq_num'] = str(i)
        # data['language'] = '韩语'
        # data['download_url']['episode_name'] = f'{name}.{seq_num}.mp4'
        data = generate_media_assets(name, douban_id=douban_id,
                                        language=language, episode_name=f'{episode_name}.{seq_num}', seq_num=seq_num)
        # data = get_key_value('[8]动漫', '[1]多剧集', '烈车战队粤语版', '2014', '1', f'{i}', area='日本', language='粤语', douban_id='25769206')
        print(data)
        insert_to_db(db_handle, data)


if __name__ == '__main__':
    url_list = [
        {'name': '20210108', 'url': 'https://www.bilibili.com/video/BV1qy4y127bC'},
        {"name": "20210115", "url": "https://www.bilibili.com/video/BV1Bv411W7yr"},
        {"name": "20210122", "url": "https://www.bilibili.com/video/BV1hz4y1S7td"},
        {"name": "20210129", "url": "https://www.bilibili.com/video/BV1Dz4y1m7Mf"},
        {"name": "20210205", "url": "https://www.bilibili.com/video/BV1wT4y1N7zQ"},
        {"name": "20210219", "url": "https://www.bilibili.com/video/BV12N411X7bL"}
    ]
    director = '이지원 박미연 변진선'
    main_actor = '金炳万 卢宇镇 秋成勋 朴正哲 MIR 朴率美 朴'
    main_actor_list = main_actor.split(' ')
    key_map['name'] = '金炳万的丛林法则2013'
    key_map['video_type'] = '[6]综艺'
    key_map['album_type'] = '[1]多剧集'
    key_map['area'] = '韩国'
    key_map['year'] = '2013'
    key_map['seq_num'] = '1'
    key_map['poster'] = 'https://www.tv4.cc/upload/vod/20200623-1/3c412f7142810556468dea9a51b80e20.jpg'
    key_map['director'] = director
    key_map['main_actor'] = main_actor_list
    key_map['details'] = '《金炳万的丛林法则3》本季“亚马逊篇”炳万族长将带领新成员MBLAQ成员MIR（房哲镛），女演员朴帅眉（又译：朴率美，下同）和2季老成员演员朴正哲、搞笑艺人卢宇镇、特种格斗选手秋成勋一组6人前往位于南美洲的拥有世界上流量最大、流域面积最广的河－－亚马逊，在那个有拇指般大毒蚂蚁、毒虫到处乱跑；各种的蛇和周围潜伏着鳄鱼以及只有在亚马逊生态界才能见到的食人鱼、水虎鱼，多种多样奇特的植物、动物的地方，显现出与之前完全不同强度的生存挑战！ 丛林IN“新西兰”将继续带着新加入的成员演员朴宝英、李必模、郑锡元和回归的老成员RICKY金一同炳万、佑镇、正哲前往生存的PARADISE－－新西兰，在那里与已经消失的“毛利族”（音译）学习只在新西兰当地的生存的独特法则后，踏上回归“初心”的路，丢弃所有的现代文明，只靠着自己的双手和新石器时代的工具，依靠着前几季的生活经验，新一代的炳万族能否顺利的生存下来？请拭目以待！ 喜马拉雅篇启程，只听说过却从没用自己的眼睛看过的美丽传说，挑战那不一般的“高度”吧！前韩国足球选手安贞焕，演员郑俊、金彗星、吴智恩在炳万族长的带领下向你介绍不一样的喜马拉雅，请期待他们的活跃！'
    key_map['download_url']['episode_name'] = f"{key_map['name']}.mp4"
    # print(key_map)

    # for i in url_list:
    # for i in range(1, 9):
    #     url = f'https://www.bilibili.com/video/BV1144y167iZ?p={i}'
    #     # url = i["url"]
    #     seq_num = f'{i}'
    #     # if i < 10:
    #     #     seq_num = f'0{i}'
    #     # else:
    #     #     seq_num = str(i)
    #     data = generate_media_assets('我买了一个农场', douban_id='34839005', seq_num=seq_num,
    #                                  download_url=url, language='英语', episode_name=f'我买了一个农场.{seq_num}')
    #     data.pop('download_state')
    #     print(data)
    #     insert_to_db(db_handle, data)

    # db_handle = db.hktv_video_info
    # db_handle = db.bde4_video_info
    db_handle = db.bilibili_video_info
    # db_handle = db.media_asserts_info_iqiyi

    name = '人类清除计划3'
    douban_id = '26101255'
    # insert_tv_series(db_handle, name, douban_id, 10, episode_name=name)
    insert_movie_data(db_handle, name, douban_id, episode_name=name)
    # insert_to_db(db_handle, key_map)
