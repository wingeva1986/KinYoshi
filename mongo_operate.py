# coding=utf-8
import json
import pymongo
from utils.CommonUtils import read_all_sheet


def unset_state(colletion, **kwargs):
    name = kwargs.get('name', '')
    seq_num = kwargs.get('seq_num', '')
    seq_list = kwargs.get('seq_list', [])
    status = kwargs.get('status', '')
    _filter = kwargs.get('filter', {})
    
    if _filter:
        filter_dic = _filter
    else:
        filter_dic = {}
        if name:
            filter_dic['name'] = name
    if seq_num:
        filter_dic['seq_num'] = str(seq_num)
    if seq_list:
        filter_dic['seq_num'] = {"$in": seq_list}
    if status:
        filter_dic['download_state.status'] = str(status)

    if ('name' in filter_dic.keys() and not filter_dic['name']) or ('download_state.status' in filter_dic.keys() and not filter_dic['download_state.status']):
        print(f'missing name or status!')
        return

    try:
        print(f'filter={filter_dic}')
        colletion.update_many(filter_dic,{
            "$unset": {
                "download_state": {"$exists": True}
            }
        })
        print(f'unset state success!')
    except BaseException as e:
        print(f'unset state error, {e}')


def add_sort(colletion, sort: int=30, **kwargs):
    name = kwargs.get('name', '')
    seq_num = kwargs.get('seq_num', '')
    seq_list = kwargs.get('seq_list', [])
    _filter = kwargs.get('filter', {})

    if _filter:
        filter_dic = _filter
    else:
        filter_dic = {"name": name}
    if seq_num:
        filter_dic['seq_num'] = str(seq_num)
    if seq_list:
        filter_dic['seq_num'] = {"$in": seq_list}
    
    try:
        print(f'filter={filter_dic}')
        colletion.update_many(filter_dic, {
            "$set": {
                "sort": sort
            }
        })
        print('add sort success!')
    except BaseException as e:
        print(f'add sort error, {e}')



if __name__ == '__main__':
    data_source = '192.168.2.9'
    intranet = '104.194.8.94'
    extranet = '104.194.11.183'
    client = pymongo.MongoClient(host=data_source, port=27117)
    client.admin.authenticate("svcadmin", "admin#svc2020")
    tp_cms_db = client.tp_cms_db
    tp_media_assert_db = client.tp_media_assert_db
    
    # col = tp_media_assert_db.cooldrama_video_info
    # name = 'sukeban deka series 2'
    # seq_list = ['2', '37']
    # status = '4'
    # unset_state(col, name, seq_list=seq_list, status=status)
    # add_sort(col, name, seq_list=seq_list)

    # 修改状态为1的数据
    # unset_state(col, status='0')

    data = read_all_sheet('episodes.xlsx')
    df = data.loc[:, ('专辑名称', '季', '内容提供方', '年代', '缺集', '状态')]
    df = df.fillna(value=0)
    for index, row in df.iterrows():
        episodes_str = row['缺集']
        status = row['状态']
        if status == '补齐' or status == '已有完整版' or status == '没有资源':
            continue
        data = {
            'name': row['专辑名称'],
            'seasons': str(int(row['季'])) if row['季'] else '',
            'year': str(int(row['年代'])) if row['年代'] else '',
            'download_state.status': '4'
        }
        episode_list = episodes_str.split(',')
        episode_list = [i for i in episode_list if i]
        
        if row['内容提供方'] == 'www.hktv03.com':
            col = tp_media_assert_db.hktv_video_info
        elif row['内容提供方'] == 'www.taijutv.com':
            col = tp_media_assert_db.taijutv_video_info
        elif row['内容提供方'] == 'www.bde4.com':
            col = tp_media_assert_db.bde4_video_info
        elif row['内容提供方'] == 'www.bilibili.com':
            col = tp_media_assert_db.bilibili_video_info

        unset_state(col, filter=data, seq_list=episode_list)
        add_sort(col, filter=data, seq_list=episode_list)
