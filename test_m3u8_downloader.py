# coding=utf-8
from urllib.parse import urljoin
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
        def pase_bde4_url(url: str, headers: dict = None, timeout: int = 60):
            headers = {'User-Agent': choice_agent()} if not headers else headers
            try:
                content = ''
                response = requests.get(
                    url, headers=headers, timeout=timeout,
                    allow_redirects=False, verify=False, proxies=get_proxy()
                )
                if response.status_code == 200:
                    content = response.text
                elif response.status_code == 302 or response.status_code == 301:
                    return pase_bde4_url(response.headers['Location'], headers)
                if not content.startswith('#EXTM3U'):
                    content = zlib.decompress(response.content[3354:], 16 + zlib.MAX_WBITS).decode('utf-8')
                return m3u8.loads(content) if content else ''
            except BaseException as e:
                print(f'pase bde4 play url error, {e}')
                return ''

        from pathlib import Path
        from m3u8_parser import M3u8Parser
        logger.info('download url %s', url)
        headers = kwargs.get('headers', {'User-Agent': choice_agent()})
        provider = kwargs.get('provider', '')
        thread_num = kwargs.get('thread_num', 10)
        headers = header_list_to_dic(headers) if isinstance(headers, list) else headers
        logger.info('headers -> %s', headers)
        logger.info('download %s output_dir=%s', output, Path(output).parents[0])
        
        if provider.find('bde4') >= 0:
            m3u8_obj = pase_bde4_url(url, headers)
            try:
                urls = [urljoin(url, i) for i in m3u8_obj.segments.uri]
                keys = [urljoin(url, key.uri) for key in m3u8_obj.keys if key]
                iv_list = [urljoin(url, key.iv) for key in m3u8_obj.keys if key]
            except BaseException as e:
                urls, keys, iv_list = [], [], []
        else:
            m3u8_parser = M3u8Parser(url, headers=headers)
            urls = m3u8_parser.get_ts_list()
            keys = m3u8_parser.get_keys()
            iv_list = m3u8_parser.get_iv()
        if not urls or not isinstance(keys, list):
            logger.info('ts downloaded result=False')
            return False
        if len(keys) < 2:
            key = keys and keys[0] or None
            keys = [key for _ in range(len(urls))]
        if len(keys) != len(urls):
            logger.info('ts downloaded result=False')
            return False
        download_res, _ = bde4_download(urls, output, headers=headers, keys=keys, thread_num=thread_num, iv_list=iv_list, proxies=False)
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
    # BDE4M3u8Downloader
    # m3u8_url = 'https://www.mp4er.com/F3DC3DBAE3D9C51191AFADC53565F819FB6400B3C55D68F9C887B441DE6A1B7D37A0274EBE1E15E970E93ECA366FE7A0033211E3AF74A40AE3F2F7256EAA39B316428952FC74B0F32228F6151EC1A9DDF324A3E77A4B049AAE15429C974C157E.m3u8'
    # https://www.mp4er.com/10E79044B82A84F70BE1308FFA5232E4460DE9564FAA63773ACFEA5D33AEFC10C7871D05FA888BEB37226D8FC7193DB0.m3u8
    m3u8_url = 'https://vod6.wenshibaowenbei.com/20210908/1H3Yvdpd/1000kb/hls/index.m3u8?skipl=1'
    data = {'url': '#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531168ae098a2945361eaff808983bb5d424a4bf4833369ae387d438deb877c85083690e58c4f8771badcca4b2320da40ce93567035f2953905854c0a1c3b9571d5fea6\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a1186e79ba2965361eef181859ba75c464d45fc802b70a86a2c4885ef8a0da1593597bf8f1ad13fa7d8ca4e7423dc109c97502532ff90681edb520307709675d5b2ebfa\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530148fe09ea2965761e9fd858883ba57464d46f3853369ae387d438deb8a7cdd5563c6b88c4ed571ee88981c2e76dc42c89e512567a9c43e05854c0a1c3b9571d5fea4\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a1f8fed99a2955161edf8838299a75c424341f0862b70a86a2c4885ef8a0da1596292edda49833fa78a981b23278e149bc3527234af943918db520307709675d5b2ebfc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f118ce09ca2964978e9f1869e9fb85b494e43f6992a6ffc69764b89e6fb0cd10b3195b98e1a9c38bbdecd497125d612cbc3077237ff94275b9b45115738917199b7\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1388e59fa2955361eefa81899ca75d434a4af6802b70a86a2c4885ef8a0ea1596693e9894ad06da78d984b75228e159fc45d7a68ffc56f1adb520307709675d5b2ebfe\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1087e79da2955361e9fe808783bb5c404f42fc833369ae387d438debdf7cd25c3592e48b13d771be8e9f1a2f728910cac0052163f2973a05854c0a1c3b9571d5fea0\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5391587e59fa290497fe6fd868183ba56474b40f28f3369ae387d438deb887cd00866c1e589198671bd82c9122273d71b9bc0542766fb9f3805854c0a1c3b9571d5feaf\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311788ed98a2955161eaff818983ba58414f4bfd813369ae387d438deb867c865f3697bb8812d671bb8bc21e2f288b1a9b96507662fd953f05854c0a1c3b9571d5feae\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f118fec9ba2945361e9ff878983ba56454b41f3853369ae387d438deb877cd10936c1e5d31e8771bc8f9f4b76738a14cf90017669fb943805854c0a1c3b9571d5fea6f8\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1e8fe29da2965661e9fe818883bb5f424d40f3853369ae387d438debdf7cd50c65c0ec8c138271be8fcc122328dc1a9f91072635ac923005854c0a1c3b9571d5fea6f9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530128ee79ea2955061e9fe848783ba5a474340fc8f3369ae387d438debdd7cd65b33c6ead81fd571bed8ca1a7321df14ccc2017434f9c63c05854c0a1c3b9571d5fea6fa\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53c1e8be598a2965461edf885879ea75c444e4bf2852970a86a2c4885ef8a5aa10e3495b8d24e8669a78899497625de1bcd96557535ae913f1cdb520307709675d5b2ebf9ca\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531138bec91a293497beaf0859e9eb156444844f4992a6ffc69764b89bbfb0bd10c3e92bedc4f9c6eb18fce1c2471891acfc7537733fc92275b9b45115738917199b3a3\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530138de19fa2955f61e9fe828183ba5a414c4afd853369ae387d438debdd7cd10c3e93e8d31d8671e983cb1a21748a159f95017664ae953b05854c0a1c3b9571d5fea6fd\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301189e19ba2955261eafe8b8383bb5a484341f3853369ae387d438debdb7c875f36c7b9db19d771ee8c994b2426df119d9f007337fc926b05854c0a1c3b9571d5fea6fe\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53d1488e098a2965261edf886859ba75d414247f0852970a86a2c4885ef8a5ca15f30c3ed884ed569a7d89f1a27768d139dc0562065acc4391fdb520307709675d5b2ebf9ce\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e0381386ed86b997497febf0838983ba57484241f1853369ae387d438dea8f7cd05a65c3ea884f8271b8dece1c2024d611cb91517330a8956a05854c0a1c3b9571d5fea6f0\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e23c1186fb98ba88577eeffd809e9fb85a44434af0992a6ffc69764b88effb5cdd0864c8e98e1c9c66bb8c9f182074db129d90517b34a99e275b9b45115738917199b3ae\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1489e098a2965661eefa82859da75c464941fc812970a86a2c4885ef8b09a15464c3bed91d836aa7d9ce4b2376dc119a95027b69f89f3b12db520307709675d5b2ebfac9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f118ee79ca2955561eaf0818783bb5f494b46f1853369ae387d438dea8c7c800e3ec8bbd91ed271badfcd1f26248c45cf96542066a8c26a05854c0a1c3b9571d5fea5f9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531108ee09fa2945e61eafe838283bb5e434943f08f3369ae387d438dea8d7cdc5f3190e48c1d8171be8f9f182475d81a9b9f5c7b37fa906d05854c0a1c3b9571d5fea5fa\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53c108fe290a29e497ceffd878983ba57454f44fc873369ae387d438dea8d7c805f61c5e88c12d571bd8bcd4b7173dc41c894537032fa923d05854c0a1c3b9571d5fea5fb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311587e49fa2965261eafc8b8183bb5c484f47f2873369ae387d438dea8d7c825d64c1b98c138271b18acb4f7228d947c89e012061aec63005854c0a1c3b9571d5fea5fc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f158cec9da2945e61eefa82869aa75d454a40f0812d70a86a2c4885ef8b0fa1086193eed21e856fa7d9ce1a7625dc1b9d95547065f9943848db520307709675d5b2ebfacc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301187e59ca2935661eaff838683bb5e454340f28f3369ae387d438dea8b7c860b3793bbd24d8371bcde981a22288d13c693022563fdc23005854c0a1c3b9571d5fea5fe\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530148fe59ba2965361e9fd8b8083ba58414c47f0873369ae387d438dea887c825a62c6e9d21ed071bc8bce4f7529da1acf96532032fec26a05854c0a1c3b9571d5fea5ff\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f178ce199a2955261eefa81849ca75c494844f0852570a86a2c4885ef8b0fa15a6394b98b4fd16aa7829b1b2e22db169894557167afc66c18db520307709675d5b2ebfac1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301486e79fa2945361e9ff828083bb5e484843f0833369ae387d438dea897c805c3ec1edd9188371eed8c21d2075d7409bc3007432af966b05854c0a1c3b9571d5fea5f1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531148aed99a29f497be9f1819e9ebb56474c44fc992a6ffc69764b88e8fb00825c31c1eb8b189c3bea82c24e2674dd46c697077165f2c1275b9b45115738917199b1a7\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311388e69ba2935661eafe868683bb5e454f43f0833369ae387d438dea877c85556195eadd1f8371b188cc1a73768a17cf91517565f8906f05854c0a1c3b9571d5fea4f9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53e1786e790a2955361e8f8878083bb5c45424bf1813369ae387d438deadf7c85083090bc8f1a8671eb889e137173de15cec4022532af933005854c0a1c3b9571d5fea4fa\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311388ed9ea2965561eafe828283ba59434c43f48f3369ae387d438dea877cdc0e6697eadd4f8b71ebd99f1a24258b17cc97027768f9933a05854c0a1c3b9571d5fea4fb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301f8ae090a2945361eaff8b8383bb5f484a46f3813369ae387d438deadd7cd70c32c3bcda4e8571ecdbc91c2f75d9139894527264f9923d05854c0a1c3b9571d5fea4fc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311789e398a2945f61eaff858683ba59414f40f68f3369ae387d438deadf7cd05b3793e4891cd071ba8bcf4f2524de17ce965d7465f3c56a05854c0a1c3b9571d5fea4fd\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1186e698a29f4978e9fd829e9eb058424846fc992a6ffc69764b88bdfb0e855830c0e9d31f9c6aba8bc24f2e72d615ca925c7535f89e275b9b45115738917199b1a1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53e178ee498a2965e61e8fa878883bb5f454e40f48f3369ae387d438deadd7cd4096595ebde48d271e98ac34e7625dc10ccc75d2163fb9f3c05854c0a1c3b9571d5fea4ff\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53c1289e39aa2955461edf880869ba75c484e45fc872570a86a2c4885ef8b5ca10f3ec3e9d81f8b6fa78f991f7127d747c7c5577a65ff976b13db520307709675d5b2ebfbc1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301e8bec90a2955661eaf8818783ba58424b41f3813369ae387d438deada7c815f63c9edda49d071ea829e1e2274d6409890502061f9926c05854c0a1c3b9571d5fea4f1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531128fe186be97497feef0858383ba5c464b4bf4873369ae387d438deadb7c825464c4eadd4fd071eb8dce1e7520da12cbc5052667f9966d05854c0a1c3b9571d5fea3f8\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301289e599a29e4978e9f9809e9ebd5c45484af0992a6ffc69764b88bafb0bdc5e3195e8884a9c38ec8dc2127427d713cc92062563fa9f275b9b45115738917199b6a6\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a108bec9aa2965661eef1828794a75c484243f68e2f70a86a2c4885ef8809a10c3595e4d312856aa788cb4e7127dd179a97062062ac91681edb520307709675d5b2ebfccb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1e88e59fa2954978eafb849e9ebc5e424d4bf2992a6ffc69764b88b9fb0e87583497ea894f9c6cbb89cd4f2f27db1b9a915d2530ff9e275b9b45115738917199b6a4\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a1389e59aa2965361eef085859fa75d444e47f2832570a86a2c4885ef880ba15a62c3eb881cd16ea783cd1b2e72da12c8c3052260f3c16b1ddb520307709675d5b2ebfccd\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53b108ae391a2955161eefe87869ca75c484f46f0802b70a86a2c4885ef8808a10b3693b9891d856fa78d9b4c2375da409bc7022066fe923b4adb520307709675d5b2ebfccc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1086e198a2914978e9fd839e9eb05f474e47f2992a6ffc69764b8becfb0185093593b9d84f9c38ee8d9b4c2f73d94698c2512633fb96275b9b45115738917199b6a1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1588e39da2955661eefa82889aa75d444a47f0842b70a86a2c4885ef880aa15b32c1bb894f8b3da782c84c7328d914c8c0517568fdc36f1ddb520307709675d5b2ebfcce\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1e8ce691a2965561e9fd8b8583bb5f424347f6873369ae387d438de98d7cd10e62c8be8b13d271bede9c482372dc46cb9e077767afc63f05854c0a1c3b9571d5fea3f0\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301e8be591a2955361eafe8b8883ba5b424240fc833369ae387d438de98a7cd55a65c0e4884a8671eadecb137626dd179c97577b69fac63c05854c0a1c3b9571d5fea3f1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1587e199a2955361eefa828794a75d414d4bf0872570a86a2c4885ef880ca15d6297b9db4d836ba789c81a23718b41cac5532735a9c63a1ddb520307709675d5b2ebfdc9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f138ce29ca295497fedfa828783bb5f45424bf6873369ae387d438de9897cdd0f3095efdb4a8571ea8ac21a2222d6179897067b65f8903e05854c0a1c3b9571d5fea2f9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301487ec9aa2954978e8f8869e9fb95a484843f2992a6ffc69764b8be7fb5b865531c3e48f4d9c67eed99e1b74718e1a9b9f057768fe95275b9b45115738917199b7a5\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301789e190a2965661e9fe878283bb5f424944fc873369ae387d438de9887cd5553fc7efde128a71ebd898492725dd13cdc2062132f9c56f05854c0a1c3b9571d5fea2fb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531138ee69ba296497ae7fb879e9fbb58474342f4992a6ffc69764b8be8fb5dd55d3197ed8e4f9c6bb98dca1375748e479b91057a30fd96275b9b45115738917199b7a3\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531158ae199a2955561eafe838083ba5b404f41f2873369ae387d438de9877c875f61c1ef8c1ad771ea8ecd1b7171db40c9c7052132a9926c05854c0a1c3b9571d5fea2fd\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a1087e399a29f497fe6fe808283ba56414342f4833369ae387d438de9867cd7096597e489188371bc8fc21324228d16cec5062565ac903a05854c0a1c3b9571d5fea2fe\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311389e19ea2945461eafe838483ba56454d43fc873369ae387d438de9df7cdd0f36c7e4884ad071be8bcc132421dd1b9897012035ac913d05854c0a1c3b9571d5fea2ff\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530148de491a2924978e9ff869e9eb057434345f6992a6ffc69764b8bbdfb5fd75a65c3e88b4d9c67ec8dc94c25768a12ca93007369fd97275b9b45115738917199b7af\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53e1187e686bc9e4977e6f9829e9eb05a464c46f0992a6ffc69764b8bbcfb0bdd5a36c0b9d3139c6cb9dbcd4975218d12cb94577160a894275b9b45115738917199b7ae\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301588e791a2965561e9fc8a8883ba56464c47f48f3369ae387d438de9dd7cd25d6692b9d84a8b71ea889c1a76728e17ccc5567b62af906a05854c0a1c3b9571d5fea1f8\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311589ed9ca2955361eaff818983ba5d414940fc833369ae387d438de9dc7cd50e62c6bfdd4d8a71bed9c2127375df45cbc3012568ff926b05854c0a1c3b9571d5fea1f9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530168be59aa2965e61e9fe8b8583ba56434b4bfc8f3369ae387d438de9db7cdd5f34c7ebd21f8671eb8d9f487627db179c94537732ff966b05854c0a1c3b9571d5fea1fa\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311486e798a2945661eafe848583bb5e464c41f3853369ae387d438de9db7cd00c6594ec8c1e8171ebd8ce482e27de11c7c3002663a89f3105854c0a1c3b9571d5fea1fb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530148de19aa2945161e9fe858483ba59484a42f7813369ae387d438de9d87c810e3092e4d94f8571ba8e9e4e2471de129b91507730af9f3d05854c0a1c3b9571d5fea1fc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530118ce390a290497be8f9819e9fbb5d414a45f6992a6ffc69764b8aeffb0d855f3394eb8e4f9c67bf8cc24e2f298d479a90522567a8c4275b9b45115738917199b4a2\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301488e399a2945561e9fe838683ba58424346f68f3369ae387d438de9d87c870e30c0e5dc138471badfce1974748c169b9f5c2769fec53d05854c0a1c3b9571d5fea1fe\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531178bed99a2945061eafe8b8883ba56474b4af1853369ae387d438de88e7c855a62c1ed8e4d8771eb82c21a7124d6469fc3537362f29f3c05854c0a1c3b9571d5fea1ff\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311088e39fa2965e61eafe818583ba58414240f6873369ae387d438de88c7c805a3e94eb8c4f8671eddf98127628dc1bc691522669f2c63f05854c0a1c3b9571d5fea1f0\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531108fe399a2945661eafe878783ba58454c47fc833369ae387d438de88d7c865435c7ecdc19d571edd8ca18212789129c97527360fc9f3105854c0a1c3b9571d5fea1f1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e731138fe286bf94497fe9f8878483bb5b444841f28f3369ae387d438de88d7cd55d6192efdc18d571eddfc21820298e42c89e572660a8943805854c0a1c3b9571d5fea0f8\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301787e49aa2965e61e9fd8a8183bb5b404946f0873369ae387d438de88a7c800b33c2e989198671badecb4b2424d6139f95002068f2c23105854c0a1c3b9571d5fea0f9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1287e49ea293497fedfa8b8283b95f414c46fd813369ae387d438de88d7cd15930c6e5dc1f8171b18f9e1272258d1bcac7027762fd933105854c0a1c3b9571d5fea0fa\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530168ce09ba2965061e9fe808183ba5e484c47f5813369ae387d438de88b7c875a33c1b9db1f8371b882c24e7476d716cdc3517561fac26b05854c0a1c3b9571d5fea0fb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531128fe586bc934977e8ff829e9ebb5a464b4afc992a6ffc69764b8aeafb0ed55b3e90ed89189c6cbe8aca4827738e139bc3527669fcc4275b9b45115738917199b5a3\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1e8ee69aa2965561e9fe8a8483b957454d46f4873369ae387d438de88b7cd15b3392eedb1d8271eedfcd1a7223d917ccc7557160f9953c05854c0a1c3b9571d5fea0fd\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f138ee29fa2955161eefa82889ba75f454241f7872d70a86a2c4885ef890ca15c3ec3e5dd1ad76ca78d991323258b12cc91077a60ac9f6a1fdb520307709675d5b2ebffcf\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301386e498a2945661e9fc8a8083ba59474f42f7853369ae387d438de8897cd45e6293bedc1d8b71be89c21f20248c1bc892567a63f8913805854c0a1c3b9571d5fea0ff\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301287e49ca2934978e9f1879e9db958414946f0992a6ffc69764b8ae9fb0fd75531c2e88e499c6ded89ce1f2f728d13989e512661f3c2275b9b45115738917199b5af\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a1288e09ea2945f61eef184869ea75c404a44f6872d70a86a2c4885ef890ea15f6494eed31a8b67a78fcc4e2574d61acf97512668ab976a19db520307709675d5b2ebffc0\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1f8ce790a2945561e9fe818883b95f494e45f5813369ae387d438de8887c865433c5bedd1d8a71b98ccb1f2128df159f97057065f8906805854c0a1c3b9571d5feaff8\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a168ce19aa294497fe6fb848583b95d494b47f1853369ae387d438de8897c865462c8eb8f488371b1d89c1d7675d71bc996017560fc903005854c0a1c3b9571d5feaff9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1089e49aa2965561eefa83869fa75c444b4af1862b70a86a2c4885ef8900a15c3ec2efd913d566a7df9c1a2026dc1aca96007a64a99e3b48db520307709675d5b2ebf0cb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311686e29ca2955461eafe8b8783bc57464c46f3813369ae387d438de8dc7cd25a65c6b9db1a8071b9dcce1972258c419d92527562ff913c05854c0a1c3b9571d5feaffb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530168ce79ca2955561e9fd8b8983bb57404845f2833369ae387d438de8dc7c875e33c3be8e1a8771ead89f1d2422db129fc5002533f2976f05854c0a1c3b9571d5feaffc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301486ec9ca2945261e9fe878783bc56444345f6873369ae387d438de8da7c825f3794b9dd1a8171eedfce1c2e74d945ca9e572632f9973e05854c0a1c3b9571d5feaffd\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f128ae19aa2955e61eefa828898a75d484a44f7842f70a86a2c4885ef895aa10c3692ebd34ed138a7d89e4f2073df1b9d9e547764f3c13b4fdb520307709675d5b2ebf0cf\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f138fe498a2955f61eefa82849ca75d474a45f28f2570a86a2c4885ef895da15963c5b8db19d568a78cce1b2429db16cb92502232f9c63048db520307709675d5b2ebf0ce\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301787e49ba2945461e9fe818083bb5b444347f7853369ae387d438de8db7c810b36c3bed21d8671eb8ac91a7320dd11cf90532163f8c26805854c0a1c3b9571d5feaff0\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f158ae09ba29e497feef0858583bb5c404940f4833369ae387d438de78e7cd00b66c2ef894e8b71ba88c8192f75d846cfc3012163f8973c05854c0a1c3b9571d5feaff1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531148fe79ea293497be9fd829e9fb059484842f4992a6ffc69764b85edfb5c825b34c3edd34f9c3fbc8aca1220208c13cdc2577365fac5275b9b45115738917199bba7\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530138aec9ea2934978e9f9859e9ebb5c43494bf6992a6ffc69764b8ab9fb0edc5c3693ef8b189c67ea8d981b7321d8149cc45d2067fe93275b9b45115738917199bba6\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1787e591a2955161eefa82869ea75d454942f7862b70a86a2c4885ef8608a10c3795e4d21d826da7de9c4e2529d711cdc35c7435ab9f6f4fdb520307709675d5b2ebf1cb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531128be590a2965661eaff838583ba56464e42f3853369ae387d438de78f7cdc5561c0eddc1dd571b8db98482627da149894577233ff973f05854c0a1c3b9571d5feaefb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530108de19ea2965161eaff848783bb59434c46f0833369ae387d438de78a7c85596492e8df1ad571ba8c9f192e268a40c691502067f3c23105854c0a1c3b9571d5feaefc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531158ae39ba2955461eafd858983bb5a424840f6833369ae387d438de78d7cdd0e3392eddc1ad671eed9984c7123de1b9b93072237a8c23005854c0a1c3b9571d5feaefd\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531138fed99a295497be9f8869e9fba5d474c41f2992a6ffc69764b85ebfb5c865f31c7bed3199c38bb8f9e487626db139d95537234f291275b9b45115738917199bba1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530178be590a2965161e9fd8a8683ba5b434942f3813369ae387d438de78a7c875e3ec1ea8b48d571b882c3482720d816ca92067433fd913905854c0a1c3b9571d5feaeff\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531148de39aa290497be9fe8b9e9eb15c464340f4992a6ffc69764b85e8fb0e815f33c2b9d21d9c6cec8fcc1c2326d9409f91502667a8c1275b9b45115738917199bbaf\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f158be09aa29f497fedfa838783bb5c444f4afc873369ae387d438de7887cdc5c6494e9dc1b8571ec8b9c1b75758c419a92567765ff9f3c05854c0a1c3b9571d5feaef1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301f8eec91a291497be8fb8a9e9fbf5e454b4bf6992a6ffc69764b85e7fb0fd1553594eedc1f9c6eb8d8994e27758917cb9f502732f2c4275b9b45115738917199b3a7f8\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1088e79da2955f61eefa82879fa75d434d47f1872970a86a2c4885ef860ea1093095eadb1e806aa7df9e4e2572d614cc96027466fac63f4fdb520307709675d5b2ebf9c99d\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531138fe399a2955361eaff818183bb59404845f1853369ae387d438de7877cd35c3395b88e498571e98ecc1c7274dc169d9f517032f9963105854c0a1c3b9571d5fea6f8cb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530148ae39da2955761e9fd848483bb5b424a41fd853369ae387d438de7877cd65c33c1efd9198771b98cc9122026dc41cf97077637abc13a05854c0a1c3b9571d5fea6f8ca\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5391288e19ea293497fe6fe808483bb5e454b42f5813369ae387d438de7df7cd30c3ec4b988488271b9dece1b2e20d8179b94067233fec23005854c0a1c3b9571d5fea6f8cd\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a118be09aa2945561eef181829ea75c464c41f3812570a86a2c4885ef865fa15f3ec2bbdd198168a7dbcc192e25df14c6c4552663fcc53e19db520307709675d5b2ebf9c999\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a118fe19da2945e61eef1878194a75c464a4bf4832570a86a2c4885ef865ba15a3192b8de1cd669a78c9c1922228e47c69e002666afc63f1adb520307709675d5b2ebf9c99a\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f148ee39ea290497fedf8818183bb5f484c4af08f3369ae387d438de7dd7cd6556692efde12d671bd8e9c1e72738a1bc79f527133fa976a05854c0a1c3b9571d5fea6f8ce\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a1287ed98a2965761eef18a8995a75d454e40fc8f2d70a86a2c4885ef865da1583395e4d318846ba78b994821228c46cdc0007765f9c36c49db520307709675d5b2ebf9c994\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301489e29ba29f4978e8f88a9e9ebd59444c42fc992a6ffc69764b85bbfb0a82593593e5da1c9c6fee8c9f1e2e278e149bc2537568ac93275b9b45115738917199b3a7f1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301187e19ca2945e61eafe8b8683ba5d494d47f6873369ae387d438de7db7cd25f34c1bb8f488a71e9df9b4921298e179d9e002562f9c36a05854c0a1c3b9571d5fea6f9c9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f138ee29da2955261eefa828598a75c464947fd832970a86a2c4885ef865ca10e32c0eedc1e8466a78d98132e27dd47cf9e537533fac43b49db520307709675d5b2ebf9c89d\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530168ae19da2945461e9ff828683ba59494340f2833369ae387d438de7d87cd65963c8b98b1bd771ba8cc2127271d617cb9e552533ff913c05854c0a1c3b9571d5fea6f9cb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311287e79ca292497beafe859e9ebf5d494840fc992a6ffc69764b84effb0ed4083590bf8f1e9c6bb18d9f1b20258d15c9c3512763f893275b9b45115738917199b3a6fb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e23f1587fb9fa296567fecfe9c839abb57424f42ea802c3dad627e428d9adc0d87586195eedf04d76cbc88994e7473d615ccc75c2666f8897945925e5a543c913dd4b3a3\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5311387ec9ba2955161eafd8b8383ba5a434d45f3853369ae387d438de68f7c825b66c5ed881ad771ed8b99182f29d81b9a97557b33f8963105854c0a1c3b9571d5fea6f9cc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53d118ae386bc9f4977e7f8849e9fb859444941f6992a6ffc69764b84ecfb58d25b65c6ebdf189c3aec8acb1927768c15cdc4012069fd96275b9b45115738917199b3a6fe\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531138ae39aa2935661eafe838283bb5f47484af6873369ae387d438de68c7cd75863c6bedb1a8071bb8bc91e7628da46cbc2557030fb976b05854c0a1c3b9571d5fea6f9ce\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1086e790a2934978e9fa8a9e9ebc58434242fc992a6ffc69764b84ecfb0ad6596594eadf1f9c6ebcd8cc487525db47ce94522130ae97275b9b45115738917199b3a6f0\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531148ae29aa2965661eafd878083ba59464c46fc873369ae387d438de68d7c81553ec9bed81c8071bb8acd4e7275d747c7c4012233f8943805854c0a1c3b9571d5fea6f9c0\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530118de49ea2945061eaff868283ba5a464940f1813369ae387d438de68a7c870934c7b9de4ad271b8839e122622d640ca955c7235ac9e6b05854c0a1c3b9571d5fea6fac9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531108ae299a29f497beafd8a9e9ebc58494240f0992a6ffc69764b84eafb08d30c62c1ee8c199c3fbb8f9c1b7129df41cf95557763f891275b9b45115738917199b3a5f9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5391f87e49aa2965261eef182869ba75c484c42f7862b70a86a2c4885ef870fa15e3695e88818d669a78f9e1b24718e15c9935c7432ab94391ddb520307709675d5b2ebf9cb9e\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e539148ce49da293497fe6f88a8283bb5c404f42fc833369ae387d438de6897cd3553fc7bb891ed571eed9c21973238e46cbc3002233fec46b05854c0a1c3b9571d5fea6faca\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530178be591a29f4978e9f9849e9fbb5b454f43f6992a6ffc69764b84e8fb5fd35c3f90e5db1c9c38bf8ece4922748b1b9ac0522760aec4275b9b45115738917199b3a5fc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530128ee198a2945161e9fe838883bb5a484a4bf5853369ae387d438de6df7cd15e65c5e5de1cd071bbdc9e1225238b14cc97512137af946c05854c0a1c3b9571d5fea6facc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301e8fe290a2965261eaf0838183ba57474e47f5853369ae387d438de6867c810932c5e4d918d071e98f9e1f7327dd13c695512237fc936c05854c0a1c3b9571d5fea6facf\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a1e88ed98a29e497fe6fe878183ba5a484341fc873369ae387d438de6877cd20b6395e4db4ad571ecdb9f1e722489459897542069fec23105854c0a1c3b9571d5fea6face\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301e8fec9fa2955061eafe808183bb5f494d42fd853369ae387d438de6df7cd0543ec6e5da128771bdd99e482e288a47c996552763acc56f05854c0a1c3b9571d5fea6fac1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e539118de59aa2955561eef1848098a75d414240f1862b70a86a2c4885ef875ba10f3fc0ead912863aa78d9b122f24d710ce95057237ff97391adb520307709675d5b2ebf9cb95\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530108be79da2965f61eaff868983ba5840424bf08f3369ae387d438de6dc7cdd083694b9881fd771e98d994e21208a419fc35c2669af9e3905854c0a1c3b9571d5fea6fbc9\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53a108ee09ca29e497fe7f0818383bb5d434240f2873369ae387d438de6dd7c81093595ef8f1ad571edd89b1e74768b15c797577232a8976a05854c0a1c3b9571d5fea6fbc8\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5381e89e299a290497fe8fe808583bb5e474b43f6833369ae387d438de6db7c810c62c1ec8f198271e9dcce1f2627db47cdc75d7a66a8c63105854c0a1c3b9571d5fea6fbcb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f1e8fe59fa2904978e8fa869e9eb05b494340f0992a6ffc69764b84bafb5bd65f32c9efd31f9c6ebadb984e7375d947c89f5d7568fcc5275b9b45115738917199b3a4fb\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301e8ae19fa290497be9ff859e9fbe58434a44f4992a6ffc69764b84b9fb0fd55a3593ea8f4d9c6bb0dfc31b24738e41cd94077335f894275b9b45115738917199b3a4fc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530118ce199a2965461eaff858383ba5a464944f7853369ae387d438de6d87cd75e35c2e5d21dd671b88ac84e76288e1198c2067a62a9923c05854c0a1c3b9571d5fea6fbcc\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f148de399a2945061eefa82869da75c474844fd8e2f70a86a2c4885efdf09a15830c2bed8128a67a7dcce4f7427dc47ccc3502168fc923049db520307709675d5b2ebf9ca9a\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e53f118ee090a2965561e9fe818383bb5e464f40f7853369ae387d438dbe8f7cd75465c6ee891cd771bc8bc81224758d1acf97027135f3c46d05854c0a1c3b9571d5fea6fbce\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e531128ee490a2945f61eafe858683bc5d464842f1813369ae387d438dbe8c7c805a35c4ec8f4d8571e98fcf4b7575db149bc5512063af956d05854c0a1c3b9571d5fea6fbc1\n#EXTINF:10.427778,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e530108ae19da2965f61eaff868783bc5c444f46fd813369ae387d438dbe8d7c860862c3ea894a8771b0dcc9492123d616cfc3002663f9c46805854c0a1c3b9571d5fea6fbc0\n#EXTINF:8.884467,\nhttps://jxn2.178du.com/hls/file/ts/1e50ba5ab60ca5a30ef0d121976b100f385365e7b70ad9ff59838327747886a2c804a60711a1c25bb894311b27773e5985bda52416841fbb554403e270cb14e77ce11251646611d5f17cf662e5301489e09fa2965261e9fe8a8183ba5c404944f48f3369ae387d438dbe8f7cd35c6393ed8b12d171bb88cb1321278d1accc3012662fe933a05854c0a1c3b9571d5fea6fcc9\n#EXT-X-ENDLIST\n\n', 'headers': ['user-agent:Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.15 (KHTML, like Gecko) Chrome/24.0.1295.0 Safari/537.15', 'referer:https://www.hktv03.com/'], 'type': 'yb_nostand'}
    BDE4M3u8Downloader().download(data['url'], f'E:\\YunBo\\鬼上你架車粤语版.s1e1.162238287290809220.ts',
                        headers=headers, thread_num=10)

    # from Crypto.Cipher import AES
    # url = 'https://wdoc-75389.picgzc.qpic.cn/MTMxMDI2NzQ3NDE0NTYyMzE_242814_795iHs-RygI9z7Fh_1593182106?imageView2'
    # key_url = 'https://pl.tcc-interiors.com/key/6faa9ae6a431ac68b0c896851088655b.key'
    # content = requests.get(key_url, headers=headers, verify=False).content
    # print(content)
    # print(len(content))
    # key = AES.new(content, AES.MODE_CBC, content)

    # res_byte = requests.get(url, headers=headers, timeout=360, verify=False).content
    # print(len(res_byte))
    # print(len(res_byte) % 16)
    # resp_bytes = key.decrypt(res_byte)
    # file_header = b'G@'
    # position = resp_bytes.find(file_header)
    # resp_bytes = resp_bytes[position:]
    # with open('1.ts', 'wb') as f:
    #     f.write(resp_bytes)

    # for i in range(1, 46):
    #     url = f'https://www.2hanju.com/player/514_1_{i}.html'
    #     response = requests.get(
    #         url, headers=headers, timeout=120
    #     )
    #     selector = Selector(text=response.text)
    #     play_url = selector.xpath('//div[@class="playleft"]/iframe/@src').get()
    #     play_url = 'https://www.2hanju.com' + play_url
    #     play_res = requests.get(play_url, headers=headers, timeout=120)
    #     download_url = re.findall(r"purl = '(.*?)';", play_res.text)[0]
    #     if download_url:
    #         BDE4M3u8Downloader().download(download_url, f'E:\\YunBo\\你笑了.{i}.ts', headers=headers)
    #     time.sleep(1)
