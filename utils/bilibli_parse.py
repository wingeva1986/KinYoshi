# -*- coding: utf-8 -*-
# @Author      : LJQ
# @Time        : 2020/10/30 10:41
# @Version     : Python 3.6.4
import abc
import json
import logging.handlers
import re
from http.cookiejar import CookieJar
from pathlib import Path
from threading import RLock

import requests
from requests.utils import dict_from_cookiejar

parent_dir = Path(__file__).parent
log_path = parent_dir / 'log'
log_path.mkdir(parents=True, exist_ok=True)
handler_rotate = logging.handlers.TimedRotatingFileHandler(log_path / "bilibili_parser.log", when="D", interval=1,
                                                           encoding='utf-8', backupCount=3)
handler_rotate.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '[%(asctime)s %(filename)s][line:%(lineno)d] [%(process)d-%(threadName)s-%(thread)d:] %(levelname)-8s %(message)s')
handler_rotate.setFormatter(formatter)
log_config = dict(
    level=logging.DEBUG,
    format=('%(asctime)s %(filename)s[line:%(lineno)d] '
            '[%(process)d-%(threadName)s-%(thread)d:] %(levelname)-8s %(message)s'),
    datefmt='%Y-%m-%d-%H:%M:%S',
    handlers=[handler_rotate]
)
logging.basicConfig(**log_config)
logger = logging.getLogger(__name__)

cookies_path = parent_dir / 'cookies/bilibili.txt'
logger.info(f'cookies_path: {cookies_path}')

RE_playInfo = re.compile(r'<script>window.__playinfo__=({.+?})</script>')
RE_state = re.compile(r'window.__INITIAL_STATE__=({.*?});')


class VideoTypeError(Exception):
    """视频类型错误"""


class CookieExpiredError(Exception):
    """cookie过期错误"""


class OtherError(Exception):
    """其他错误"""


class Messages(object):
    normal = 'normal'
    cookie_expired = 'cookie_expired'
    no_subtitles = 'no_subtitles'
    cant_download = 'cant_download'
    need_pay = 'need_pay'
    video_type_error = 'video_type_error'
    other_error = 'other_error'
    duration_too_short = 'duration_too_short'

    def __getitem__(self, index):
        variables = []
        for variable in self.__class__.__dict__:
            if variable.startswith('__') and variable.endswith('__'):
                continue
            variables.append(variable)
        return variables[index]


class BaseType(metaclass=abc.ABCMeta):
    def __init__(self, data: dict):
        self.data = data

    def parse(self):
        """特定视频类型解析"""


class DASHType(BaseType):
    def parse(self):
        dash = self.data['dash']
        video_url = sorted(dash['video'], key=lambda x: x['id'])[-1]['base_url']
        audio_url = dash['audio'][0]['base_url']

        return {
            'video': {
                'urls': [video_url],
                'headers': {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/86.0.4240.111 Safari/537.36",
                    "Accept": "*/*",
                    "Origin": "https://www.bilibili.com",
                    "Referer": "https://www.bilibili.com/",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
                'type': 'several_mp4s_download'
            },
            'audios': [{
                'urls': [audio_url],
                'headers': {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/86.0.4240.111 Safari/537.36",
                    "Accept": "*/*",
                    "Origin": "https://www.bilibili.com",
                    "Referer": "https://www.bilibili.com/",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
                'type': 'several_mp4s_download'
            }],
            'type': 'audios_video_merge'
        }


class FLVType(BaseType):
    def parse(self):
        flvs = self.data['durl']
        urls = [flv['url'] for flv in flvs]
        return {
            'urls': urls,
            'headers': {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/86.0.4240.111 Safari/537.36",
                "Accept": "*/*",
                "Origin": "https://www.bilibili.com",
                "Referer": "https://www.bilibili.com/",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            'type': 'several_mp4s_download'
        }


# class MP4Type(BaseType):
#     def parse(self):
#         # TODO: 待验证
#         urls = self.data['durl'][0]['url']
#         return {
#             'urls': urls,
#             'headers': {
#                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
#                               "Chrome/86.0.4240.111 Safari/537.36",
#                 "Accept": "*/*",
#                 "Origin": "https://www.bilibili.com",
#                 "Referer": "https://www.bilibili.com/",
#                 "Accept-Language": "zh-CN,zh;q=0.9",
#             },
#             'type': 'single_url_stream_download'
#         }


SUBCLASS_MAP = {subclass.__name__[:-4].lower(): subclass for subclass in BaseType.__subclasses__()}


def video_type_factory(data: dict) -> BaseType:
    video_type = 'flv'
    if (data.get('format') or '').find('mp4') > -1:
        video_type = 'mp4'
    if 'dash' in data:
        video_type = 'dash'
    elif 'dash_mpd' in data:
        video_type = 'dash'

    if video_type not in SUBCLASS_MAP:
        raise VideoTypeError(video_type)
    return SUBCLASS_MAP[video_type](data)


class BiLiBiLi(object):
    _lock = RLock()

    def __init__(self, play_url: str):
        self._cookie = None
        self.session = requests.session()
        self.session.cookies.update(self.get_cookie_dict(self.cookie))
        self.play_url = play_url

    @property
    def cookie(self):
        with self._lock:
            with open(cookies_path, 'r', encoding='utf-8') as f:
                self._cookie = f.read()
        return self._cookie

    @cookie.setter
    def cookie(self, cookies):
        with self._lock:
            if isinstance(cookies, CookieJar):
                cookies = dict_from_cookiejar(cookies)
            if isinstance(cookies, dict):
                cookie = []
                for k, v in cookies.items():
                    cookie.append(f'{k}={v}')
                cookies = '; '.join(cookie)
            with open(cookies_path, 'w', encoding='utf-8') as f:
                f.write(cookies)

    @staticmethod
    def get_cookie_dict(cookies: str):
        cookie_dict = {}
        for c in cookies.split('; '):
            k, v = c.split('=', 1)
            cookie_dict[k] = v
        return cookie_dict

    def _get_ep_data(self, ep_info):
        params = {
            "cid": ep_info['cid'],
            "qn": '116',
            "type": "",
            "otype": "json",
            "fourk": "1",
            "bvid": ep_info['bvid'],
            "ep_id": ep_info['id'],
            "fnver": "0",
            "fnval": "80",
            "session": "08658c0614521439332e22c68dfb7857"
        }
        api = 'https://api.bilibili.com/pgc/player/web/playurl'
        headers = {
            "Host": "api.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/86.0.4240.111 Safari/537.36",
            "Origin": "https://www.bilibili.com",
            "Referer": "https://www.bilibili.com/",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        resp_dict = self.session.request('get', api, headers=headers, params=params).json()
        if resp_dict.get('message') == '大会员专享限制':
            raise CookieExpiredError(resp_dict)
        elif resp_dict.get('message') != 'success':
            raise OtherError(resp_dict)
        return resp_dict

    def _get_data(self):
        headers = {
            "Host": "www.bilibili.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/86.0.4240.111 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;"
                      "q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        resp_str = self.session.request('get', self.play_url, headers=headers).content.decode('utf-8')
        try:
            ep_info = json.loads(RE_state.search(resp_str).group(1))['epInfo']
        except Exception:
            data = json.loads(RE_playInfo.search(resp_str).group(1))['data']
        else:
            data = self._get_ep_data(ep_info)['result']
        return data

    def parse(self):
        vinfo = dict()
        message = Messages.normal
        try:
            data: dict = self._get_data()
            # print(json.dumps(data))
            subclass = video_type_factory(data)
            if subclass:
                vinfo = subclass.parse()
            else:
                message = Messages.video_type_error
        except CookieExpiredError:
            message = Messages.cookie_expired
        except OtherError:
            message = Messages.other_error
        except VideoTypeError:
            message = Messages.video_type_error
        except Exception:
            message = Messages.cant_download
        return [{
            "message": message,
            "vinfo": vinfo,
        }]


if __name__ == '__main__':
    # u = 'https://www.bilibili.com/video/BV1Pt411b7kN'
    # u = 'https://www.bilibili.com/bangumi/play/ep93274'
    # u = 'https://www.bilibili.com/video/BV1AK411L7YW'
    u = 'https://www.bilibili.com/video/BV1Zp4y1h7uu?from=search&seid=18312121186451816170'
    # u = 'https://www.bilibili.com/bangumi/play/ep318867'
    # u = 'https://www.bilibili.com/bangumi/play/ep93274'
    r = BiLiBiLi(u).parse()
    print(json.dumps(r))
    # print(SUBCLASS_MAP)
