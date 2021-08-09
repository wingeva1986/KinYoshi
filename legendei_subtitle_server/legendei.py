# coding=utf-8
import time
from datetime import time
import re
import sys
import difflib
import logging
import math
import requests
from lxml import etree

sys.path.append('.')
sys.path.append('..')
from utils.util_agent import choice_agent

logger = logging.getLogger(__name__)

REMOVE_PATTERN = re.compile('|'.join([
        r'BRRip',
        r'BDRip',
        r'BRrip',
        r'BluRay',
        r'WEB-DL',
        r'WEBRip',
        r'HDRip',
        r'DVDScr',
        r'WEB',
        r'- CAM',
        r'720p',
        r'1080p',
        r'Temporada Completa'
    ]))
MOVIE_NAME_PATTERN = re.compile(r'(.*?) \(.*?\)')
SERIES_NAME_PATTERN = re.compile(r'(.*?S\d+)E\d+')
SEASON_PU_PATTERN = re.compile(r'(\d+)ª')


class Legendei(object):
    def __init__(self):
        self.headers = {'user-agent': choice_agent()}

    @staticmethod
    def get_equal_rate(str1, str2):
        ''' 两个字符串的相似度 '''
        return difflib.SequenceMatcher(None, str1, str2).quick_ratio()

    def format_name(self, name: str):
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
            video_name = f'{series_name} S0{seasons}' if int(seasons) < 10 else f'{series_name} S{seasons}'
        if video_name.find('/') >= 0:
            name_list += [name.strip() for name in video_name.split('/')]
        else:
            name_list += [video_name]
        return name_list

    def subtitle_search(self, keyword: str, **kwargs):
        '''
        return {
            "keyword": keyword,
            "search_res": [
                {"full_name": full_name, "name_rate": name_rate, "detail_url": detail_url, "subtitle_url": subtilte_url}
            ]
        }
        '''
        # https://legendei.to/category/filmes/page/1/?s=The%20Outpost
        # https://legendei.to/category/series/page/1/?s=The+Outpost
        video_type = kwargs.get('video_type', '')
        if video_type.find('电影') >= 0:
            base_url = 'https://legendei.to/category/filmes/page/1/'
        elif video_type.find('电视剧') >= 0:
            base_url = 'https://legendei.to/category/series/page/1/'
        else:
            base_url = 'https://legendei.to/page/1/'
        url = f'{base_url}?s={keyword}'

        data_list = []
        logger.info(f'Search url: {url}')
        response = requests.get(url, headers=self.headers)
        res_data = etree.HTML(response.text)
        data_list.append(res_data)
        last_urls = res_data.xpath('//span[@class="pages"]/text()')
        if last_urls:
            try:
                total_page = re.compile(r'Página 1 de (\d+)').search(last_urls[0]).group(1)
                if int(total_page) > 40:
                    total_page = math.ceil(int(total_page) / 2)
                for page in range(2, int(total_page) + 1):
                    page_url = re.sub(r'page/(\d+)/', f'page/{page}/', url)
                    logger.info(f'Search url: {page_url}')
                    page_res_str = requests.get(page_url, headers=self.headers).text
                    page_data = etree.HTML(page_res_str)
                    data_list.append(page_data)
                    time.sleep(.5)
            except BaseException as e:
                logger.warning(f'get detail content error, {e}')

        res_item = {"keyword": keyword, "search_res": []}
        for data in data_list:
            result_list = data.xpath('//div[@class="simple-grid-posts simple-grid-posts-grid"]/div/div/div/div/h3')

            for result in result_list:
                detail_url = result.xpath('a/@href')[0]
                full_name = result.xpath('a/text()')[0]
                logger.info(f'name:{full_name}, detail_url={detail_url}')
                video_name_list = self.format_name(full_name)
                logger.info(f'\nfull name: {full_name}\nformat name: {video_name_list}')

                # 多剧集获取seq_nums
                if re.compile(r'(E\d+\-E\d+)').search(full_name):
                    episode_num_list = re.findall(r'E(\d+)', full_name)
                else:
                    episode_num_match = re.compile(r'E(\d+)').search(full_name)
                    episode_num_list = [episode_num_match.group(1)] if episode_num_match else []
                
                # detail_con_list = detail_data.xpath('//div[@class="entry-content clearfix"]/p/text()')
                # detail_con = ''.join(detail_con_list)
                # logger.info(detail_con)
                # handle_name = '.'.join(keyword.replace(':', '').split(' '))
                # name_ret = keyword.upper() in [name.upper() for name in video_name_list]

                # 拿处理好后的所有名字和keyword比较获取相似度
                mutil_name = {"full_name": full_name, "info": [{
                    "name": name,
                    "name_rate": self.get_equal_rate(keyword, name)
                } for name in video_name_list]}
                if [i for i in mutil_name["info"] if i["name_rate"] > 0.9]:
                    mutil_name['detail_url'] = detail_url
                    mutil_name['subtitle_url'] = self.get_subtitle_url(detail_url)
                    # mutil_name['seq_num'] = '-'.join(episode_num_list) if episode_num_list else ''
                    res_item["search_res"].append(mutil_name)
                logger.info(f'mutil_name = {mutil_name}')
        return res_item


    def get_subtitle_url(self, detail_url: str, **kwargs):
        subtitle_url = ''
        detail_str = requests.get(detail_url, headers=self.headers).text
        detail_data = etree.HTML(detail_str)
        sub_url_list = detail_data.xpath('//a[@class="buttondown"]/@href')
        if not sub_url_list:
            sub_url_list = detail_data.xpath('//a[@class="rcw-button-0 rcw-medium orange "]/@href')
            if not sub_url_list:
                sub_url_list = detail_data.xpath('//a[@class="rcw-button-0 rcw-large orange "]/@href')
        if sub_url_list:
            subtitle_url = sub_url_list[0]
            if not subtitle_url.startswith("http"):
                subtitle_url = detail_url + subtitle_url
        return subtitle_url


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    legendei = Legendei()
    keyword = 'The Pond'

    res = legendei.subtitle_search(keyword)
    logger.info(res['keyword'])
    for i in res["search_res"]:
        logger.info(i)
    # logger.info(res['subtitle_urls'])