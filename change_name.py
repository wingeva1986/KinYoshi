# coding=utf-8
import os
import re
import shutil
import pymongo
from pathlib import Path


data_source = '192.168.2.9'
client = pymongo.MongoClient(host=data_source, port=27117)
client.admin.authenticate("svcadmin", "admin#svc2020")
db = client.tp_media_assert_db
db_handle = db.bde4_video_info

info = db_handle.find({'name': '若你安好便是晴天'})

target_dir = 'E:\BaiduNetiskDownload\新兵日记'

file_list = []
for root, dirs, files in os.walk(target_dir, topdown=False):
    for i in range(len(files)):
        file_path = Path(root) / Path(files[i])
        tail_type = files[i].split('.')[-1]
        # print(file_path)
        seq_num = re.findall(r'E(\d+)\.', files[i])
        try:
            if int(seq_num[-1]) < 10:
                seq_num = str(seq_num[-1]).replace('0', '', 1)
            if int(seq_num[-1]) >= 10:
                if str(seq_num[-1]).startswith('0'):
                    seq_num = str(seq_num[-1]).replace('0', '', 1)
                else:
                    seq_num = seq_num[-1]
        except:
            seq_num = seq_num[-1]

        # item = {}
        # movie_list = db_handle.find({"name": "降龙伏虎小济公第一季"})
        # for movie in movie_list:
        #     item[movie['seq_num']] = movie['download_url']['episode_name']
        # print(item[seq_num])

        new_name = f'新兵日记.{seq_num}.{tail_type}'
        new_path = Path(root) / Path(new_name)
        # print(new_path)
        # movie_name = new_name
        # new_path = Path(root) / Path('.'.join([remove_special_symbols(movie_name), str(i + 1), 'mp4']))
        print(f'old_name={file_path}\nnew_name={new_path}\n')
        shutil.move(file_path, new_path)

