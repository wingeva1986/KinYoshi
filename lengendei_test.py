# coding=utf-8
import re
from bson.py3compat import iteritems
import requests
import pymongo
import logging
import math
import pandas as pd
from lxml import etree

from utils.util_agent import choice_agent
requests.packages.urllib3.disable_warnings()
logger = logging.getLogger(__name__)


REMOVE_PATTERN = re.compile('|'.join([
    r'BRRip',
    r'BDRip',
    r'BRrip',
    r'HDRip',
    r'HDrip',
    r'BluRay',
    r'WEB-DL',
    r'WEBRip',
    r'WebRip',
    r'HDRip',
    r'HDTV',
    r'DVDScr',
    r'DVDRip',
    r'LEGENDAS',
    r'WEB',
    r'WEBDL'
    r'- CAM',
    r'CAM',
    r'720p',
    r'1080p',
    r'HDTS',
    r'Temporada Completa'
]))
MOVIE_NAME_PATTERN = re.compile(r'(.*?) \(.*?\)')
SERIES_NAME_PATTERN = re.compile(r'(.*?S\d+)E\d+')
SEASON_PU_PATTERN = re.compile(r'(\d+)ª')
MONGODB_URL = "mongodb://svcadmin:admin%23svc2020@104.194.8.94:27117/?authSource=admin&readPreference=primary&ssl=false"
client = pymongo.MongoClient(MONGODB_URL)
col = client['tp_media_assert_db']['torrentool_info']
legendei_col = client['tp_media_assert_db']['legendei_info']


def format_name(name: str):
    name_list = []
    try:
        video_name = MOVIE_NAME_PATTERN.search(name).group(1).strip()
    except:
        try:
            video_name = SERIES_NAME_PATTERN.search(name).group(1).strip()
        except:
            video_name = name
    if REMOVE_PATTERN.search(video_name):
        video_name = REMOVE_PATTERN.sub('', video_name).strip()
    if SEASON_PU_PATTERN.search(video_name):
        name_list.append(video_name)
        series_name = SEASON_PU_PATTERN.sub('', video_name).strip()
        seasons = SEASON_PU_PATTERN.search(video_name).group(1)
        video_name = f'{series_name} S0{seasons}' if int(
            seasons) < 10 else f'{series_name} S{seasons}'
    if video_name.find('/') >= 0:
        name_list += [name.strip() for name in video_name.split('/')]
    else:
        name_list += [video_name]
    return name_list

def get_equal_rate(str1, str2):
    ''' 两个字符串的相似度 '''
    import difflib
    return difflib.SequenceMatcher(None, str1, str2).quick_ratio()

def get_data_to_mongo():
    info_list = col.find({
        "video_type": re.compile('电影'), 
        "download_url.categories": {"$in": ['Legendada', 'Dublado | Legendada', 'Dual Áudio | Dublado | Legendada']}
    }).limit(100)
    name_list = [info['name'] for info in info_list]
    headers = {'user-agent': choice_agent()}
    base_url = 'https://legendei.to/category/filmes/page/1/'
    item = {'keyword': [], 'search_res': [], 'multi_name': [], 'subtitle_urls': [], "name_rate": []}
    res_list = []
    for name in name_list:
        url = f'{base_url}?s={name}'

        data_list = []
        logger.info(f'Search url: {url}')
        response = requests.get(url, headers=headers)
        res_data = etree.HTML(response.text)
        data_list.append(res_data)
        last_urls = res_data.xpath('//span[@class="pages"]/text()')
        
        if last_urls:
            try:
                total_page = re.compile(
                    r'Página 1 de (\d+)').search(last_urls[0]).group(1)
                if int(total_page) > 40:
                    total_page = math.ceil(int(total_page) / 2)
                for page in range(2, int(total_page) + 1):
                    page_url = re.sub(r'page/(\d+)/', f'page/{page}/', url)
                    logger.info(f'Search url: {page_url}')
                    page_res_str = requests.get(
                        page_url, headers=headers).text
                    page_data = etree.HTML(page_res_str)
                    data_list.append(page_data)
            except BaseException as e:
                logger.warning(f'get detail content error, {e}')

        res = {'keyword': name}
        search_res, video_name_list, subtitle_urls, name_rates = [], [], [], []
        for data in data_list:
            result_list = data.xpath('//div[@class="simple-grid-posts simple-grid-posts-grid"]/div/div/div/div/h3')
            for result in result_list:
                detail_url = result.xpath('a/@href')[0]
                full_name = result.xpath('a/text()')[0]
                # search_res.append(full_name)

                logger.info(f'name:{full_name}, detail_url={detail_url}')
                video_name_list = format_name(full_name)
                logger.info(f'\nfull name: {full_name}\nformat name: {video_name_list}')

                try:
                    detail_str = requests.get(detail_url, headers=headers, verify=False).text
                    detail_data = etree.HTML(detail_str)
                    sub_url_list = detail_data.xpath(
                        '//a[@class="buttondown"]/@href')
                    if not sub_url_list:
                        sub_url_list = detail_data.xpath(
                            '//a[@class="rcw-button-0 rcw-medium orange "]/@href')
                    name_ret = name.upper() in [vname.upper() for vname in video_name_list]
                    name_rates += [{'full_name': full_name,'name': vname, 'name_rate': get_equal_rate(name, vname)} for vname in video_name_list]
                    # name_in_detail_ret = detail_con.find(handle_name) >= 0 or detail_con.find(keyword) >= 0
                    # logger.info(f'\nname_rate = {name_rate}\nname_ret = {name_ret}')
                    if name_ret and sub_url_list:
                        subtitle_url = sub_url_list[0]
                        if not str(subtitle_url).startswith('http'):
                            subtitle_url = f'{detail_url}{subtitle_url}'
                        subtitle_urls.append(subtitle_url)
                except BaseException as e:
                    logger.warning(f'get data error, {e}')
        res['multi_name'] = name_rates
        res['subtitle_urls'] = subtitle_urls
        print(res)
        res_list.append(res)
        if len(res_list) >= 10:
            legendei_col.insert_many(res_list, ordered=False)
            res_list = []
    if res_list:
        legendei_col.insert_many(res_list, ordered=False)
        # res['name_rate'] = name_rate
        # item['keyword'].append(name)
        # item['search_res'].append(search_res)
        # item['multi_name'].append(video_name_list)
        # item['subtitle_urls'].append(subtitle_urls)
        # item['name_rate'].append(name_rate)

    # df = pd.DataFrame(item)
    # writer = pd.ExcelWriter('result.xlsx')
    # df.to_excel(writer)
    # writer.save()

'''
将根据keyword和搜索结果进行比较获取的相似度数据生成Excel
Column: keyword, 搜索结果, 格式化后的名字, 相似度
'''
import os
from utils.excel_util import HandleExcel
movie_items = []
excel = HandleExcel()
file_name = "test.xlsx"
outpath = os.path.abspath(os.getcwd())
legendei_info = legendei_col.find({}).batch_size(10)
for li in legendei_info:
    keyword = li['keyword']
    multi_names = li['multi_name']  
    
    for info in multi_names:
        movie_item = dict()
        movie_item['keyword'] = keyword
        movie_item['full_name'] = info['full_name']
        movie_item['format_name'] = info['name']
        movie_item['name_rate'] = info['name_rate']
        print(movie_item)
        movie_items.append(movie_item)
file_path = os.path.join(outpath, file_name)
header_row = ["keyword", "full_name", "format_name", "name_rate"]
excel.write_excel_xlsx(movie_items, header_row, file_path, header_row)
# print(file_path)