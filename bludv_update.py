import datetime
import json
from dns.rdatatype import NULL
import pymongo
import re
import time

URL145 = "mongodb://svcadmin:admin%23svc2020@104.194.8.94:27117/?authSource=admin&readPreference=primary&ssl=false"
# URL9 = "mongodb://svcadmin:admin%23svc2020@192.168.2.9:27117/?authSource=admin&readPreference=primary&ssl=false"

# cms = pymongo.MongoClient(URL145).get_database('tp_cms_db').get_collection('cms_video_info')
col = pymongo.MongoClient(URL145).get_database('tp_media_assert_db').get_collection('torrentool_info')

multi_audio_categories = [
    'Dual Áudio | Dublado',
    'Nacional',
    'Dublado',
    '',
    'Dual Áudio',
    'Dublado | Nacional',
    'Dual Áudio | Dublado | Nacional'
]
has_legendada_categories = [
    'Legendada',
    'Dublado | Legendada',
    'Dual Áudio | Dublado | Legendada'
]
def statistics():
    print('昨天下载量:', col.count({
        'download_state': {'$exists': True},
        'scrapy_date_str': re.compile((datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d'))
    }))
    statistics_list = []
    for video_type in ["[1]电影", '[2]电视剧', '[8]动漫']:
        multi_audio_filter = {
            'video_type': video_type, 
            "download_url.categories": {"$in": multi_audio_categories},
        }
        legendada_filter = {
            'video_type': video_type,
            "download_url.categories": {"$in": has_legendada_categories},
        }
        # 多音轨的总数
        multi_audio_total_count = col.count(multi_audio_filter)
        # 有字幕的总数
        legendada_total_count = col.count(legendada_filter)

        # 要下载的多音轨
        # {"tmdb_id": {"$ne": ""}, "download_url.url": {"$nin": [None, '']}, "download_url.is_4k": False}
        can_download_filter = {
            **multi_audio_filter, 
            **{"tmdb_id": {"$ne": ""}, "download_url.url": {"$nin": [None, '']}, "download_url.is_4k": False}
        }
        can_download_count = col.count(can_download_filter)
        # 没有download_url字段
        dont_has_durl_filter = {'video_type': video_type, "download_url": None}
        dont_has_durl_count = col.count(dont_has_durl_filter)
        # 多音轨中不需要下载的
        dont_need_download_filter = {
            **multi_audio_filter,
            **{"$or": [{"tmdb_id": ""}, {"download_url.is_4k": True}]}
        }
        dont_need_download_count = col.count(dont_need_download_filter)
        download_dont_need_filter = {
            **multi_audio_filter,
            **{'download_state': {"$exists": True}},
            **{"$or": [{"tmdb_id": ""}, {"download_url.is_4k": True}]},
        }
        # 下载中
        downloading_filter = {**multi_audio_filter, **{'download_state.status': '1'}}
        downloading_count = col.count(downloading_filter)
        # 下载成功
        download_sucess_filter = {
            **multi_audio_filter,
            **{'download_state.status': '2'}
        }
        download_count = col.count(download_sucess_filter)
        # 下载失败
        download_error_filter = {
            **multi_audio_filter,
            **{'download_state.status': '4'}
        }
        error_count = col.count(download_error_filter)
        # 未下载的
        dont_downloaded_filter = {**can_download_filter, **{'download_state': {"$exists": False}}}
        dont_downloaded_count = col.count(dont_downloaded_filter)

        statistics_list.append(
            {video_type: {
                '下载成功': download_count,
                '下载失败': error_count,
                '下载中': downloading_count,
                '要下载的多音轨': can_download_count,
                '多音轨还没下载的': dont_downloaded_count,
                '不下载的多音轨(4k, 无tmdb_id, 无下载地址)': dont_need_download_count,
                '不下载的多音轨但是下载了': col.count(download_dont_need_filter),
                '多音轨总数': multi_audio_total_count,
                '有字幕总数': legendada_total_count,
                '字幕下载成功': col.count({**legendada_filter, **{'download_state.status': '2'}}),
                '字幕下载失败': col.count({**legendada_filter, **{'download_state.status': '4'}}),
                '总数': col.count({"video_type": video_type}) - dont_has_durl_count
            }}
        )
        # print({**legendada_filter, **{'download_state.status': '2'}})
    return statistics_list


if __name__ == '__main__':
    r = statistics()
    for i in r:
        print(json.dumps(i, indent=1, ensure_ascii=False))
    # print(json.dumps(col.distinct('video_type'), ensure_ascii=False))
    # print(col.update_many(
    #     filter={'download_state.status': '0'},
    #     update={'$unset':{
    #         'download_state': '',
    #     }}
    # ).modified_count)
