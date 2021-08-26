# coding=utf-8
import re
from pyppeter_test import main
import pymongo


pattern = re.compile('|'.join([
    r'（.*?）',
    r'\(.*?\)',
    r'(第\w+)部'
]))
def migrate_all(old_col, new_col):
    new_list = []
    for i in old_col.find({"name": pattern}).batch_size(10):
        i.pop('_id')
        new_list.append(i)
        print(i["name"])
        if len(new_list) >= 100:
            new_col.insert_many(new_list)
            new_list = []
    if new_list:
        new_col.insert_many(new_list)


if __name__ == '__main__':
    mongo_url = "mongodb://svcadmin:admin%23svc2020@192.168.2.9:27117/?authSource=admin&readPreference=primary&ssl=false"
    extranet_mongo = "mongodb://svcadmin:admin%23svc2020@104.194.8.94:27117/?authSource=admin&readPreference=primary&ssl=false"
    client = pymongo.MongoClient(mongo_url)
    db = client['tp_media_assert_db']
    jumi_col = db['jumi_video_info']
    extranet_client = pymongo.MongoClient(extranet_mongo)
    extranet_db = extranet_client['tp_media_assert_db']
    extranet_jumi = extranet_db['jumi_video_info']

    migrate_all(extranet_jumi, extranet_jumi)
