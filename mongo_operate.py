# coding=utf-8
import json
import pymongo


data_source = '192.168.2.9'
intranet = '104.194.8.94'
extranet = '104.194.11.183'


def unset_state(colletion, **kwargs):
    name = kwargs.get('name', '')
    seq_num = kwargs.get('seq_num', '')
    seq_list = kwargs.get('seq_list', [])
    status = kwargs.get('status', '')

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


def add_sort(colletion, name, sort: int=30, **kwargs):
    seq_num = kwargs.get('seq_num', '')
    seq_list = kwargs.get('seq_list', [])

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
    client = pymongo.MongoClient(host=data_source, port=27117)
    client.admin.authenticate("svcadmin", "admin#svc2020")
    tp_cms_db = client.tp_cms_db
    tp_media_assert_db = client.tp_media_assert_db
    
    col = tp_media_assert_db.cooldrama_video_info
    name = 'sukeban deka series 2'
    seq_list = ['2', '37']
    status = '4'
    # unset_state(col, name, seq_list=seq_list, status=status)
    # add_sort(col, name, seq_list=seq_list)

    # 修改状态为1的数据
    unset_state(col, status='0')
