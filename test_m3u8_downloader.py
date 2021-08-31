# coding=utf-8
import asyncio
from itertools import count  # 当异步请求返回时,通知异步操作完成
import aiohttp  # 表示http请求是异步方式去请求的
import datetime
import sys
import os
import re
import json
import requests
import logging
import time
import zlib
import pymongo
import base64
from scrapy import Selector, selector
from abc import ABCMeta, abstractmethod

import m3u8
from m3u8.model import PartInformation
from requests import api

from utils.CommonUtils import get_ts_list
from bde4_downloader import Bde4Downloader, bde4_download
from utils.m3u8_downloader import iqiyi_m3u8_download
from utils.util_agent import choice_agent
from utils.CommonUtils import header_list_to_dic, get_header_list
logger = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings()


def get_proxy():
    # 隧道代理
    url = 'http://tps.kdlapi.com/api/gettps/?orderid=909125905835865&num=1&format=json&sep=1'
    # 隧道域名:端口号
    tunnel = requests.get(url).json()['data']['proxy_list'][0]
    # 用户名密码方式
    username = 't19125905835963'
    password = 'ggrxcogm'
    proxies = {
        "http": "http://%(user)s:%(pwd)s@%(proxy)s/" % {"user": username, "pwd": password, "proxy": tunnel},
        "https": "http://%(user)s:%(pwd)s@%(proxy)s/" % {"user": username, "pwd": password, "proxy": tunnel}
    }
    return proxies


def parse_m3u8_url(url: str, headers: dict):
    '''
    parse m3u8 url get m3u8 content
    :param url:
    :param headers:
    :return:
    '''
    content = ''
    try:
        response = requests.get(
            url, headers=headers, allow_redirects=False, proxies=get_proxy(), verify=False)
        if response.status_code == 200:
            content = response.text
        elif response.status_code == 302:
            real_m3u8_url = response.headers['Location']
            response = requests.get(real_m3u8_url, headers=headers)
            content = response.text
            if not content.startswith('#EXTM3U'):
                content = zlib.decompress(
                    response.content[3354:], 16 + zlib.MAX_WBITS).decode('utf-8')
    except BaseException as e:
        logger.warning(f'parse m3u8 url error {e}')
    return content


class downloader_interface(object):
    __metaclass__ = ABCMeta  # 指定这是一个抽象类

    @abstractmethod  # 抽象方法
    def download(self, url, output, timeout=3600, **kwargs):
        '''
        :param url:  url to be downloaded
        :param output:  file full path to be saved
        :param timeout： timeout seconds to download
        :return:
        ret,download result, TRUE success, False fail
        '''
        ret = False
        return ret


class IQIYIM3u8Downloader(downloader_interface):
    def download(self, url, output, **kwargs):
        print('download url %s', url)
        start_time = time.time()
        print(f'开始时间:{start_time}')
        headers = kwargs.get('headers', {})
        provider = kwargs.get('provider', '')
        thread_num = kwargs.get('thread_num', 10)
        if isinstance(headers, list):
            headers = header_list_to_dic(headers)
        elif isinstance(headers, dict):
            headers = headers
        headers = {'User-Agent': choice_agent()} if not headers else headers
        logger.info('headers -> %s', headers)
        position = url.find('.m3u8')
        prefix_url = '/'.join(url[:position].split('/')[:-1])

        output_dir = '\\'.join(output.split('\\')[:-1])
        print(f'download {output} output_dir={output_dir}')
        m3u8_con = ''
        if url.startswith('http'):
            m3u8_con = parse_m3u8_url(url, headers)
            m3u8_obj = m3u8.loads(m3u8_con)
        else:
            # m3u8 提取uri和key
            m3u8_obj = m3u8.loads(url)
        urls = m3u8_obj.segments.uri
        if not urls and m3u8_con:
            host_name = '/'.join(url.split('/')[:3])
            base_url = re.findall(r'\n(.*?m3u8)', m3u8_con)[0]
            m3u8_url = f'{host_name}{base_url}'
            m3u8_con = parse_m3u8_url(m3u8_url, headers)
            m3u8_obj = m3u8.loads(m3u8_con)
            urls = m3u8_obj.segments.uri
        if not not urls:
            if not str(urls[0]).startswith('http'):
                urls = [f'{prefix_url}/{url}' for url in urls]
        keys = [key.uri for key in m3u8_obj.keys if key]
        if not not keys:
            key_list = []
            for i in keys:
                if i and not i.startswith('http'):
                    key_url = f'{prefix_url}/{i}'
                    key_list.append(key_url)
            if key_list:
                keys = key_list
        keys = [i for i in keys if not not i]
        if len(keys) < 2:
            key = keys and keys[0] or None
            keys = [key for _ in range(len(urls))]
        if len(keys) != len(urls):
            logger.info('ts downloaded result=False')
            return False
        # download_res, _ = iqiyi_m3u8_download(urls, output, headers=headers, keys=keys, thread_num=thread_num)
        download_res, _ = bde4_download(
            urls, output, headers=headers, keys=keys, thread_num=thread_num)
        end_time = time.time()
        print('ts downloaded result=%s', download_res)
        print(f'结束时间:{end_time}')
        print('耗时:', str(end_time - start_time))
        return download_res


class M3u8Downloader(downloader_interface):
    def download(self, url, output, **kwargs):
        provider = kwargs.get('provider', '')
        thread_num = kwargs.get('thread_num', 10)
        vinfo = kwargs.get('vinfo') or {}
        logger.info(f'vinfo: {vinfo}')
        headers = vinfo['headers']
        urls = vinfo['urls']
        output_dir = '\\'.join(output.split('\\')[:-1])
        logger.info('download %s output_dir=%s', output, output_dir)
        keys = [None for _ in range(len(urls))]
        download_res, _ = iqiyi_m3u8_download(
            urls, output, headers=headers, keys=keys, thread_num=thread_num)
        logger.info('ts downloaded result=%s', download_res)
        return download_res


class StandM3u8Downloader(downloader_interface):
    @staticmethod
    def header_list_to_dic(header_list: list):
        header_dic: [str] = {}
        try:
            for h in header_list:
                head: str = h
                idx = head.index(':')
                n = head[:idx].strip()
                v = head[idx + 1:].strip()
                header_dic[n] = v
        except Exception as e:
            logger.warning('header_list_to_dic error %s', e)
        return header_dic

    def download(self, url, output, **kwargs):
        callback_count = 1
        provider = kwargs.get('provider', '')
        headers = kwargs.get('headers', '')
        thread_num = kwargs.get('thread_num', 10)
        output_dir = '\\'.join(output.split('\\')[:-1])
        logger.info('download %s output_dir=%s', output, output_dir)
        logger.info(f'download_url type(str or list):{url}')
        if isinstance(headers, list):
            headers = self.header_list_to_dic(headers)
        elif isinstance(headers, dict):
            headers = headers
        headers = {'User-Agent': choice_agent()} if not headers else headers
        if isinstance(url, list):
            ts_list = url
            keys = [None for _ in range(len(url))]
        elif isinstance(url, str):
            ts_list, keys = get_ts_list(
                url, callback_count=callback_count, headers=headers)
        else:
            logger.warning(
                f'url_type: {type(url)},url:{url}.  Does not conform to the format, str or list')
            return
        download_res, _ = iqiyi_m3u8_download(
            ts_list, output, headers=headers, keys=keys, thread_num=thread_num)
        logger.info('ts downloaded result=%s', download_res)
        return download_res


class ParseM3u8:
    base = ''       # 网站根目录
    step_size = 20  # 异步步长
    total_ts = 0    # 总ts数量
    current = 1     # 正在下载ts编号
    list_ts = []
    headers = {
        # 'Connection': 'keep - alive',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36'
    }

    def __init__(self, isRealM3u8=True):
        self.isRealM3u8 = isRealM3u8

    # 设置异步步长
    def setStepSize(self, step_size):
        self.step_size = step_size

    # 功能：失败提示，失败重试，失败记录日志，线程池提高并发，超时重试。
    def start(self, url, filename):
        download_path = os.getcwd() + "\download"
        if not os.path.exists(download_path):
            os.mkdir(download_path)

        #新建日期文件夹
        download_path = os.path.join(
            download_path, datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        print("download_path: ", download_path)
        os.mkdir(download_path)
        self.path = download_path

        # 解析m3u8
        self.parseM3u8(url)

        self.total_ts = len(self.list_ts)
        step = int(self.total_ts / self.step_size) + 1
        loop = asyncio.get_event_loop()  # loop的作用是——做完任务,事件通知
        for i in range(0, self.total_ts, step):
            temp_size = self.current
            total_size = self.total_ts
            ################下载进度部分################
            done = int(50 * temp_size / total_size)
            # 调用标准输出刷新命令行，看到\r回车符了吧
            # 相当于把每一行重新刷新一遍
            sys.stdout.write("\r[%s%s] %d%%" % (
                '█' * done, ' ' * (50 - done), 100 * temp_size / total_size))
            sys.stdout.flush()

            list_step = self.list_ts[i: i + step]
            tasks = [self.download(item) for item in list_step]
            #由于是异步请求,download(item)并不会被马上执行,只是占用了一个位置
            loop.run_until_complete(asyncio.wait(tasks))
        loop.close()

        # 合并为mp4文件
        self.merge(download_path, filename)
        print(filename, "下载完成")

    def parseM3u8(self, url):
        # 根据实际情况修改(不同m3u8文件base截取方式可能不同)
        self.base = re.findall(r'(.*//.*?)/', url)[0]
        if(url[:5] != 'https'):
       	    self.base = url.rsplit("/", 1)[0] + "/"
        try:
            url_real = url
            # 得到真正的m3u8 url
            if not self.isRealM3u8:
                text_tem = requests.get(url, timeout=10).text  # 获取M3U8文件内容
                url_real = self.base + text_tem.split("\n")[2]
                # print("url_real: ", url_real)
                # 更新 base
                self.base = re.findall(r'(.*//.*?/)', url)
                if(url[:5] != 'https'):
                    self.base = url.rsplit("/", 1)[0] + "/"

            all_content = requests.get(
                url_real, timeout=10).text  # 获取第一层M3U8文件内容
            if "#EXTM3U" not in all_content:
                raise BaseException("非M3U8的链接")

            if "EXT-X-STREAM-INF" in all_content:  # 第一层
                file_line = all_content.split("\n")
                for line in file_line:
                    if '.m3u8' in line:
                        url = self.base + line     # 拼出第二层m3u8的URL
                        all_content = requests.get(url).text

            items = re.findall(r',\n(.*)\n#EXTINF', all_content)

            for item in items:
                if not str(item).startswith('http'):
                    item = self.base + item
                # print("pd_url: ", item)
                self.list_ts.append(item)
            print(len(self.list_ts), "个url解析完成")
        except Exception as e:
            print(e)
            print("重新解析m3u8")
            return self.parseM3u8(url)

    async def download(self, name):
        file_name = re.findall('.*/(.*)', name)[0]
        try:
            # print("pd_url: ", name)
            async with aiohttp.request("GET", name, headers=self.headers) as res:
                data = await res.read()

            file_path = self.path + "\\" + file_name
            with open(file_path, "wb") as f:
                f.write(data)
                f.flush()

            res.close()
            self.current += 1

        # 报错提示
        except Exception as e:
            print(e)
            print(file_name, '下载失败')

            # 记录日志
            my_log = logging.getLogger('lo')
            my_log.setLevel(logging.DEBUG)
            file = logging.FileHandler('error.log', encoding='utf-8')
            file.setLevel(logging.ERROR)
            my_log_fmt = logging.Formatter(
                '%(asctime)s-%(levelname)s:%(message)s')
            file.setFormatter(my_log_fmt)
            my_log.addHandler(file)
            my_log.error(file_name + '下载失败 ')
            my_log.error(e)

            # 重新下载
            async with self.download(name) as r:
                return

    def merge(self, path, filename):
        os.chdir(path)
        cmd = "copy /b * new.tmp"
        os.system(cmd)
        os.system('del /Q *.ts')
        os.system('del /Q *.mp4')
        os.rename("new.tmp", filename)
        os.system('cls')

def __jx_api(url_param: str):
    download_url = ''
    headers = {
        # 'Connection': 'keep-alive',
        # 'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="90", "Google Chrome";v="90"',
        # 'sec-ch-ua-mobile': '?0',
        'User-Agent': choice_agent(),
        # 'Accept': '*/*',
        # 'Sec-Fetch-Site': 'cross-site',
        # 'Sec-Fetch-Mode': 'cors',
        # 'Sec-Fetch-Dest': 'empty',
        # 'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    api_url = 'https://jx5.178du.com/8090/jiexi/api.php'
    data = {
        'url': url_param,
        'referer': 'aHR0cHM6Ly9qeC4xNzhkdS5jb20v',
    }
    logger.info(f'Request(method[POST]) {api_url}')
    try:
        response = requests.post(api_url, data=data, headers=headers)
        if response.status_code == 200:
            data = response.json()
            download_url = data['url'] if data['code'] == 200 else ''
            logger.info(f'Get -> {download_url}')
            if download_url.endswith('.html'):
                logger.info(f'Request {download_url}')
                response = requests.get(download_url, headers=headers)
                selector = Selector(text=response.text)
                jx_api_url = selector.xpath('//iframe/@src').get()
                logger.info(f'Get -> {jx_api_url}')
                if not jx_api_url.startswith('http'):
                    jx_api_url = '/'.join(download_url.split('/')
                                            [:3]) + '/' + jx_api_url
                    logger.info(f'Request {jx_api_url}')
                    jx_api_res = requests.get(jx_api_url, headers={
                        'user-agent': choice_agent(),
                        'referer': download_url
                    })
                    params_pattern = re.compile(
                        r'\$\.post\("api.php",({.*?}),', re.S).search(jx_api_res.text)
                    params_str = params_pattern.group(
                        1) if params_pattern else ''
                    api_url = '/'.join(jx_api_res.url.split('/')
                                        [:4]) + '/api.php'

                    params_url = re.findall(
                        r"'url':'(.*?)'", params_str)[0]
                    params_referer = re.findall(
                        r"'referer':'(.*?)'", params_str)[0]
                    params_time = re.findall(
                        r"'time':'(.*?)'", params_str)[0]
                    other_l = base64.b64encode(
                        params_url.encode(encoding='utf-8')).decode()
                    data = {
                        'url': params_url,
                        'referer': params_referer,
                        'time': params_time,
                        'other_l': other_l
                    }
                    logger.info(f'Get -> {data}')
                    logger.info(f'Request(method[POST]) {api_url}')
                    res = requests.post(api_url, headers={
                        'user-agent': choice_agent(),
                    }, data=data)
                    download_url = res.json()['url']
    except BaseException as e:
        download_url = ''
        logger.warning(f'jx error {e}')
    finally:
        if download_url.startswith('//'):
            download_url = 'https:' + download_url
    return download_url


def youku_download():
    headers = {
        'user-agent': choice_agent(),
    }
    response = requests.get('https://list.youku.com/show/episode?id=327137&stage=reload_201805&callback=jQuery111206441220547532585_1629080171297&_=1629080171307', headers=headers)
    res_json = json.loads(re.findall(r'\(({.*?})\)', response.text)[0])
    html = res_json['html']
    # selector = Selector(text=html)
    # play_url_list = selector.xpath('//div[@id="playList"]/div//div/a/@href').getall()
    play_url_list = re.findall(r'<dt>(.*?)<a class="c555" href="(.*?)"', html)
    for i in range(len(play_url_list)):
        if str(play_url_list[i][1]).startswith('//'):
            play_url = 'https:' + play_url_list[i][1]
        m3u8_url = __jx_api(play_url)
        print(f'm3u8_url={m3u8_url}')
        if m3u8_url:
            IQIYIM3u8Downloader().download(m3u8_url, f'E:\\YunBo\\中国梦想秀第十季.{play_url_list[i][0]}.ts',
                        headers=headers, thread_num=10)


def ktkkt_download():
    api_url = 'http://127.0.0.1:9700/parse/ktkkt'
    base_url = 'https://www.ktkkt.top'
    list_url = 'https://www.ktkkt.top/movie/index4992.html'
    res_str = requests.get(list_url, headers=headers, proxies=get_proxy()).text
    selector = Selector(text=res_str)
    episode_list = selector.xpath('//div[@id="playlist1"]/ul/li')
    for episode in episode_list[125:130]:
        episode_name = episode.xpath('a/text()').get()
        play_url = episode.xpath('a/@href').get()
        print(f'episode_name={episode_name}, play_url={base_url + play_url}')
        if play_url and episode_name:
            play_url = base_url + play_url
            episode_num = re.findall(r'(\d+)',  episode_name)[0]

            data = {
                'url': play_url
            }
            response = requests.post(api_url, data=data)
            res_json = response.json()
            print(res_json)
            IQIYIM3u8Downloader().download(
                res_json['result'][0]['urls'],
                f'E:\\YunBo\\龙珠超国语版.{episode_num}.ts',
                thread_num=10)
        time.sleep(.5)


def hktv_download():
    base_url = 'https://www.hktv03.com/'
    detail_url = 'https://www.hktv03.com/vod/detail/id/138479.html'
    res_str = requests.get(detail_url, headers=headers).text
    selector = Selector(text=res_str)
    info_list = selector.xpath('(//div[@class="myui-panel_bd clearfix"])[2]/ul/li')
    for i in info_list:
        episode_name = i.xpath('a/text()').get()
        play_url = base_url + i.xpath('a/@href').get()
        try:
            seq_num = re.findall(r'(\d+)集', episode_name)[0]
        except:
            seq_num = ''
        if seq_num and play_url:
            print(f'{episode_name}, {play_url}')
            api_url = 'http://127.0.0.1:9700/parse/hktv'
            data = {
                'url': play_url
            }
            response = requests.post(api_url, data=data)
            video_src = response.json()['result']['video_src']
            m3u8_url = video_src[0]['url']
            if m3u8_url:
                IQIYIM3u8Downloader().download(m3u8_url, f'E:\\YunBo\\僵尸道长2国语版.{seq_num}.ts',
                        headers=headers, thread_num=10)


class BDE4M3u8Downloader(downloader_interface):
    def download(self, url, output, **kwargs):
        from pathlib import Path

        def get_m3u8_obj(url):
            m3u8_con = parse_m3u8_url(url, headers)
            m3u8_obj = m3u8.loads(m3u8_con)
            target_duration = m3u8_obj.target_duration
            if target_duration:
                return m3u8_obj
            else:
                try:
                    logger.info(f'has other m3u8, need request again')
                    host_name = '/'.join(url.split('/')[:3])
                    base_url = re.findall(r'\n(.*?m3u8)', m3u8_con)[0]
                    m3u8_url = f'{host_name}{base_url}'
                    logger.info(f'other m3u8 -> {m3u8_url}')
                except BaseException as e:
                    logger.warning(f'cant find other m3u8, {e}')
                    return m3u8_obj
                return get_m3u8_obj(m3u8_url)

        logger.info('download url %s', url)
        headers = kwargs.get('headers', {'User-Agent': choice_agent()})
        provider = kwargs.get('provider', '')
        thread_num = kwargs.get('thread_num', 10)
        headers = header_list_to_dic(headers) if isinstance(
            headers, list) else headers
        logger.info('headers -> %s', headers)
        output_dir = Path(output).parents[0]
        logger.info('download %s output_dir=%s', output, output_dir)
        prefix_url = '/'.join(url[:url.find('.m3u8')].split('/')[:-1])
        m3u8_obj = get_m3u8_obj(url) if url.startswith(
            'http') else m3u8.loads(url)
        urls = m3u8_obj.segments.uri
        if not not urls:
            if not str(urls[0]).startswith('http'):
                urls = [f'{prefix_url}/{url}' for url in urls]
        keys = [key.uri for key in m3u8_obj.keys if key]
        if len(keys) < 2:
            key = keys and keys[0] or None
            keys = [key for _ in range(len(urls))]
        if len(keys) != len(urls):
            logger.info('ts downloaded result=False')
            return False
        if keys and not str(keys[0]) and not str(keys[0]).startswith('http'):
            keys = ['/'.join(url.split('/')[:3]) + key for key in keys if key and not key.startswith('http')]
        download_res, _ = bde4_download(
            urls, output, headers=headers, keys=keys, thread_num=thread_num)
        logger.info('ts downloaded result=%s', download_res)
        return download_res


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    # data_source = '104.194.11.183'
    # client = pymongo.MongoClient(host=data_source, port=27117)
    # client.admin.authenticate("svcadmin", "admin#svc2020")
    # db = client.tp_media_assert_db
    # db_handle = db.dandanzan_movie_info
    headers = {
        # 'sec-ch-ua': '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
        # 'Referer': 'https://www.mp4er.com',
        # 'sec-ch-ua-mobile': '?0',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36',
    }
    '''
    飞哥与小佛  https://www.70cn.com/tag/%E9%A3%9E%E5%93%A5%E4%B8%8E%E5%B0%8F%E4%BD%9B#
    地狱厨房    https://www.70cn.com/tag/%E5%9C%B0%E7%8B%B1%E5%8E%A8%E6%88%BF
    '''
    # IQIYIM3u8Downloader
    # m3u8_url = 'https://www.mp4er.com/F3DC3DBAE3D9C51191AFADC53565F819FB6400B3C55D68F9C887B441DE6A1B7D37A0274EBE1E15E970E93ECA366FE7A0033211E3AF74A40AE3F2F7256EAA39B316428952FC74B0F32228F6151EC1A9DDF324A3E77A4B049AAE15429C974C157E.m3u8'
    m3u8_url = 'https://vod10.bdzybf.com/20210824/BF1Lx15b/index.m3u8'
    BDE4M3u8Downloader().download('https://www.mp4er.com/10E79044B82A84F70BE1308FFA5232E4460DE9564FAA63773ACFEA5D33AEFC10C7871D05FA888BEB37226D8FC7193DB0.m3u8', f'E:\\YunBo\\833.ts',
                        headers=headers, thread_num=1)
    """
    特殊案件专案组TEN第一部
    来自星星的你（）
    不朽的名曲2（2021）
    甜蜜家园 Sweet Home
    """
    REMOVE_PATTERN = re.compile('|'.join([
        r'（.*?）',
        r'\(.*?\)',
    ]))
    # repalce_pattern = re.compile(r'(第\w+)部')
    # name = '外出(2020)'
    # print(REMOVE_PATTERN.sub('', name))
    # print(repalce_pattern.sub(repalce_pattern.search(name).group(1) + '季', name))
    # name = '外出（2020）'
    # name = '外出(2020)'
    # from Crypto.Cipher import AES
    # url = 'https://vod10.bdzybf.com/20210822/8Yaoqxap/1000kb/hls/w9CfEd9M.ts'
    # key_url = 'https://vod10.bdzybf.com/20210822/8Yaoqxap/1000kb/hls/key.key'
    # content = requests.get(key_url, headers=headers).content
    # key = AES.new(content, AES.MODE_CBC, content)

    # res_byte = requests.get(url, headers=headers, timeout=360).content
    # print(len(res_byte))
    # print(len(res_byte) % 16)
    # resp_bytes = key.decrypt(res_byte)
    # file_header = b'G@'
    # position = resp_bytes.find(file_header)
    # resp_bytes = resp_bytes[position:]
    # with open('1.ts', 'wb') as f:
    #     f.write(resp_bytes)
    # url = 'https://www.mp4er.com/F3DC3DBAE3D9C51191AFADC53565F819D18BEA97C5B3B0B880ECA9C7A8B0F8EFC6163619147641DA230B860FE01CB9ADB2E5228815CF9EB521A05F029377A3D978FF19CB72F7F7ACE0BEF34BA00D3247F324A3E77A4B049AAE15429C974C157E.ts'
    # response = requests.get(url, headers=headers, proxies=get_proxy())
    # print(response.status_code)