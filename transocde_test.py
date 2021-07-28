# coding=utf-8
import asyncio  # 当异步请求返回时,通知异步操作完成
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
from abc import ABCMeta, abstractmethod

import m3u8
from m3u8.model import PartInformation
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from media_downloader import get_ts_list
from util.excel_util import HandleExcel
from util.ffmpeg import ffprobe_get_media_info, process_audio
from util.m3u8_downloader.bde4_downloader import bde4_download
from util.m3u8_downloader.iqiyi_m3u8_downloader import iqiyi_m3u8_download
from util.util_agent import choice_agent

logger = logging.getLogger(__name__)


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
        from util.nostand_downloader import header_list_to_dic

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
    base = ''  # 网站根目录
    step_size = 20  # 异步步长
    total_ts = 0  # 总ts数量
    current = 1  # 正在下载ts编号
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

        # 新建日期文件夹
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
            # 由于是异步请求,download(item)并不会被马上执行,只是占用了一个位置
            loop.run_until_complete(asyncio.wait(tasks))
        loop.close()

        # 合并为mp4文件
        self.merge(download_path, filename)
        print(filename, "下载完成")

    def parseM3u8(self, url):
        # 根据实际情况修改(不同m3u8文件base截取方式可能不同)
        self.base = re.findall(r'(.*//.*?)/', url)[0]
        if (url[:5] != 'https'):
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
                if (url[:5] != 'https'):
                    self.base = url.rsplit("/", 1)[0] + "/"

            all_content = requests.get(
                url_real, timeout=10).text  # 获取第一层M3U8文件内容
            if "#EXTM3U" not in all_content:
                raise BaseException("非M3U8的链接")

            if "EXT-X-STREAM-INF" in all_content:  # 第一层
                file_line = all_content.split("\n")
                for line in file_line:
                    if '.m3u8' in line:
                        url = self.base + line  # 拼出第二层m3u8的URL
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


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    headers = {
        # 'Connection': 'keep-alive',
        # 'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="90", "Google Chrome";v="90"',
        # 'sec-ch-ua-mobile': '?0',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36',
        # 'Accept': '*/*',
        # 'Sec-Fetch-Site': 'cross-site',
        # 'Sec-Fetch-Mode': 'cors',
        # 'Sec-Fetch-Dest': 'empty',
        # 'Accept-Language': 'zh-CN,zh;q=0.9',
    }
    # seq_list = [21, 30, 36, 63, 64]
    # for i in seq_list:
    #     url = f'http://www.rwgaoxin.com/in/159545-1-{i}.html'
    #     try:
    #         response = requests.get(url, headers=headers)
    #         play_data = re.findall(r'var player_aaaa=(.*?)</script>', response.text)[0]
    #         m3u8_url = json.loads(play_data)['url']
    #     except BaseException as e:
    #         print(e)
    #         m3u8_url = ''
    #     if m3u8_url:
    # res = requests.get(m3u8_url, headers=headers).text
    # host_name = '/'.join(m3u8_url.split('/')[:3])
    # base_url = re.findall(r'\n(.*?m3u8)', res)[0]
    # m3u8_url = f'{host_name}{base_url}'
    from download_core.Dandanzan import DandanzanParser
    import pymongo

    parser = DandanzanParser()
    # downloader = StandM3u8Downloader()
    downloader = IQIYIM3u8Downloader()

    data_source = '104.194.11.183'
    client = pymongo.MongoClient(host=data_source, port=27117)
    client.admin.authenticate("svcadmin", "admin#svc2020")
    db = client.tp_media_assert_db
    db_handle = db.torrentool_info

    # download_list = []
    # info_list = db_handle.find({"name": "终极一班5", "seq_num": {"$gte": "55"}})
    # for info in info_list:
    #     download_list.append({"url": info["download_url"]["url"], "episode_name": info["download_url"]["episode_name"]})

    # for i in download_list:
    #     header_list = ['user-agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36']
    # video_src = parser.parse(i['url'])['video_src']
    # for j in video_src:
    #     m3u8_url = j['url']
    #     print(i["episode_name"], m3u8_url)
    #     # downloader.download(m3u8_url, f'E:\\YunBo\\{i["episode_name"]}', headers=j['headers'], thread_num=10)
    #     break

    # m3u8_url = 'https://v5.dious.cc/20210528/mS1Ht0kT/1000kb/hls/index.m3u8?skipl=1'
    # downloader.download(m3u8_url, f'E:\\YunBo\\麻辣变形计.39.ts', headers=headers, thread_num=10)
    # pm = ParseM3u8()
    # pm.start(m3u8_url, f'E:\\YunBo\\6-25-2.ts')

    # def load_data_to_excel(db_handle, outpath):
    #     movie_items = []
    #     excel = HandleExcel()
    #     file_name = "7-21.xlsx"
    #     for movie in db_handle.find({"download_state.status": "4"}).batch_size(10):
    #         movie_item = dict()
    #         movie.pop('_id')
    #         movie.pop('download_state')
    #         movie.pop('condition')
    #         for key, value in movie.items():
    #             movie_item[key] = value
    #         print(movie_item)
    #         movie_items.append(movie_item)
    #     file_path = os.path.join(outpath, file_name)
    #     header_row = list(movie_items[0].keys())
    #     excel.write_excel_xlsx(movie_items, header_row, file_path, header_row)
    # load_data_to_excel(db_handle, 'E:\\YunBo')
    SUPPORT_CHANNEL_NUMBER = 6
    # bps
    BIT_RATE_4K_MAX = 10000000
    BIT_RATE_4K = 6000000
    BIT_RATE_2K_MAX = 4000000
    BIT_RATE_2K = 1800000
    AAC_BIT_RATE_MAX = 400000
    AAC_BIT_RATE_MINIMUM = 128000
    BITE_RATE_MIINIMUM = 128000
    BITE_RATE_MEDIUM = 192000
    BITE_RATE_MAX = 320000
    src = 'E:\YunBo\\ac3_aac.ts'
    output = 'E:\YunBo\龙之家族.ts.tmp'
    media_info = ffprobe_get_media_info(src)
    video_duration = int(float(media_info['format']['duration']))
    # audio_src_list, audio_process_result = process_audio(src, output, media_info, True, timeout=3600,
    #                                                      add_dolby=True, video_duration=video_duration)

    ac3_index_list = set(
        map(lambda stream: stream['index'] if stream['codec_name'].startswith('ac3') else -1, media_info['stream']))
    eac3_index_list = set(
        map(lambda stream: stream['index'] if stream['codec_name'].startswith('eac3') else -1, media_info['stream']))
    aac_index_list = set(
        map(lambda stream: stream['index'] if stream['codec_name'].find('aac') >= 0 else -1, media_info['stream']))
    audio_index_list = set(
        map(lambda stream: stream['index'] if stream['codec_type'].startswith('audio') else -1, media_info['stream']))
    language_list = set(
        map(lambda stream: stream['language'] if stream['codec_type'].startswith('audio') else -1,
            media_info['stream']))
    ac3_index_list.discard(-1)
    eac3_index_list.discard(-1)
    aac_index_list.discard(-1)
    audio_index_list.discard(-1)
    language_list.discard(-1)
    all_ac3_list = list(ac3_index_list) + list(eac3_index_list)
    # 如果aac_index_list为空, 并且all_ac3_list的长度等于所有音轨的数量, 说明只有ac3/eac3音轨
    only_have_ac3 = False
    if not aac_index_list and len(all_ac3_list) == len(audio_index_list):
        only_have_ac3 = True

    multi_lang = True if len(list(language_list)) > 1 else False

    audio_state_list = []
    language_state = {}
    trans_aac_list, need_get_ac3_list = [], []
    if multi_lang:
        for stream in media_info['stream']:
            if stream['codec_type'].startswith('audio'):
                if stream['language'] not in language_state.keys():
                    language_state[stream['language']] = {}
                if 'has_aac' not in language_state[stream['language']].keys() or \
                        not language_state[stream['language']]['has_aac'][0]:
                    language_state[stream['language']]['has_aac'] = (True, stream['index']) if stream['codec_name'].find(
                        'aac') >= 0 else (False, 0)

                if 'has_ac3' not in language_state[stream['language']].keys() or \
                        not language_state[stream['language']]['has_ac3'][0]:
                    has_ac3 = stream['codec_name'].find(
                        'ac3') >= 0 and not stream['codec_name'].find('eac3') >= 0
                    language_state[stream['language']]['has_ac3'] = (
                        True, stream['index']) if has_ac3 else (False, 0)

                if 'has_eac3' not in language_state[stream['language']].keys() or \
                        not language_state[stream['language']]['has_eac3'][0]:
                    language_state[stream['language']]['has_eac3'] = (True, stream['index']) if stream['codec_name'].find(
                        'eac3') >= 0 else (False, 0)

                if 'has_other' not in language_state[stream['language']].keys() or \
                        not language_state[stream['language']]['has_other'][0]:
                    has_other = stream['codec_name'].find(
                        'ac3') < 0 and stream['codec_name'].find('aac') < 0
                    language_state[stream['language']]['has_other'] = (
                        True, stream['index']) if has_other else (False, 0)

        for key, value in language_state.items():
            print(key, value)
            has_aac_tuple = value['has_aac']
            has_ac3_tuple = value['has_ac3']
            has_eac3_tuple = value['has_eac3']
            has_other_tuple = value['has_other']
            if has_aac_tuple[0] and has_ac3_tuple[0]:
                both_have = True
            elif has_aac_tuple[0]:
                if not has_eac3_tuple[0] and not has_other_tuple[0]:
                    # 有aac, 但是没有ac3, eac3和其他类型, 通过aac生成这个语言的ac3
                    need_get_ac3_list.append(has_aac_tuple[1])
                elif has_eac3_tuple[0] and not has_other_tuple[0]:
                    # 除了aac, 只有eac3, 将eac3转换成aac, 并生成ac3
                    trans_aac_list.append(has_eac3_tuple[1])
                    need_get_ac3_list.append(has_eac3_tuple[1])
                elif has_other_tuple[0] and not has_eac3_tuple[0]:
                    # 除了aac, 只有其他类型, 转换成aac, 并生成ac3
                    trans_aac_list.append(has_other_tuple[1])
                    need_get_ac3_list.append(has_other_tuple[1])
            elif has_ac3_tuple[0]:
                if not has_eac3_tuple[0] and not has_other_tuple[0]:
                    trans_aac_list.append(has_ac3_tuple[1])

    print(f'需要转换成aac的列表: {trans_aac_list}')
    print(f'需要生成ac3:{need_get_ac3_list}')

    for stream in media_info['stream']:
        if stream['codec_type'].startswith('audio'):
            audio_state_dic = {
                'audio_index': stream['index'], 'codec_name': stream['codec_name']}
            if only_have_ac3:
                audio_state_dic['target_codec_name'] = 'aac'
            else:
                # 如果有其他音轨或者有eac3音轨存在就需要转成aac
                # 存在多语言的时候, 每一种语言都需要有aac和ac3音轨, 所以当某一种语言只有ac3的时候需要转成aac, 只有aac的时候需要生成ac3
                has_other_aduio = stream['codec_name'].find(
                    'aac') < 0 and stream['codec_name'].find('ac3') < 0
                if has_other_aduio or stream['codec_name'].startswith('eac3') or stream['index'] in trans_aac_list:
                    audio_state_dic['target_codec_name'] = 'aac'
                else:
                    audio_state_dic['target_codec_name'] = stream['codec_name']
            audio_state_dic['origin_bit_rate'] = stream['bit_rate']
            try:
                audio_state_dic['channels'] = int(
                    stream['channels']) if stream['channels'] and 'channels' in stream.keys() else 0
            except BaseException as e:
                audio_state_dic['channels'] = 0
            audio_state_dic['language'] = stream['language']
            # audio_state_dic['more_six_channel'] = 1 if int(stream['channels']) > SUPPORT_CHANNEL_NUMBER else 0
            audio_state_list.append(audio_state_dic)

    audio_src_list = []
    audio_process_result = False

    for audio_state in audio_state_list:
        print(audio_state)
        audio_src_dic = {}
        bit_rate = AAC_BIT_RATE_MINIMUM
        audio_tracks_list = [audio_state['audio_index']]
        audio_tmp = f'{output}_{audio_state["target_codec_name"]}_{audio_state["audio_index"]}.tmp'
        # bit_mode = audio_state['bit_mode']
        channels = int(audio_state['channels'])
        origin_bit_rate = int(audio_state['origin_bit_rate'])
        # more_six_channel = audio_state['more_six_channel']
        '''
        aac: 声道为立体声, 原码率小于128修改为128, 大于128小于400修改为192, 大于400修改为320
        ac3: 两声道的码率为192, 大于等于六声道修改为六声道码率为320, 声道数不知道则为六声道码率为320
        '''
        if audio_state["target_codec_name"].find('aac') >= 0:
            channels = 2
            if origin_bit_rate < AAC_BIT_RATE_MINIMUM:
                bit_rate = BITE_RATE_MIINIMUM
            elif origin_bit_rate < AAC_BIT_RATE_MAX:
                bit_rate = BITE_RATE_MEDIUM
            else:
                bit_rate = BITE_RATE_MAX
        if audio_state["target_codec_name"].find('ac3') >= 0:
            if not channels:
                channels = 6
                bit_rate = BITE_RATE_MAX
            else:
                if channels <= 2:
                    channels = 2
                    bit_rate = BITE_RATE_MEDIUM
                elif channels >= 6:
                    channels = 6
                    bit_rate = BITE_RATE_MAX
