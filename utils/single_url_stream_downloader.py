# -*- coding: utf-8 -*-
# @Author      : LJQ
# @Time        : 2020/11/30 20:48
# @Version     : Python 3.6.4
__all__ = ['single_url_stream_download', 'SingleURLStreamDownload']

import logging.handlers
import os
from contextlib import suppress
from pathlib import Path

import requests

log_path = Path(__file__).parent / 'log'
log_path.mkdir(parents=True, exist_ok=True)
handler_rotate = logging.handlers.TimedRotatingFileHandler(Path(log_path) / "single_url_stream_downloader.log",
                                                           when="D",
                                                           interval=1, encoding='utf-8', backupCount=3)
handler_rotate.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '[%(asctime)s %(filename)s][line:%(lineno)d] [%(process)d-%(threadName)s-%(thread)d:] %(levelname)-8s %(message)s')
handler_rotate.setFormatter(formatter)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] [%(process)d-%(threadName)s-%(thread)d:] %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d-%H:%M:%S',
                    handlers=[handler_rotate]
                    )

logger = logging.getLogger('single_url_stream_downloader')
logger.setLevel(logging.DEBUG)


def single_url_stream_download(url: str, filepath: str, headers: dict = None):
    return SingleURLStreamDownload(headers).download(url, filepath)


class SingleURLStreamDownload(object):
    def __init__(self, headers: dict = None):
        self.headers = headers

    def download(self, url: str, filepath: str):
        session = requests.session()
        logger.debug(f'下载到: {filepath}')
        with suppress(FileNotFoundError):
            Path(filepath).unlink()
            logger.info(f'删除已存在文件: {filepath}')
        seed = 0
        max_len = 100 * 1024 * 1024
        max_request_times = 100
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/85.0.4183.102 Safari/537.36'
        }
        keys = [key.lower() for key in headers.keys()]
        if 'range' not in keys:
            headers['Range'] = f"bytes=0-"

        while seed < max_len and max_request_times > 0:
            with open(filepath, 'ab') as fw:
                headers['Range'] = f'bytes={seed}-'
                retry_time = 0
                for i in range(3):
                    try:
                        response = session.request('get', url, headers=headers, stream=True)
                    except Exception as e:
                        retry_time += 1
                        if retry_time == 2:
                            logger.error(e)
                            return False
                    else:
                        break
                content_length = response.headers.get('Content-Range')
                if content_length:
                    max_len = int(content_length.split('/', 1)[-1])
                    for chunk in response.iter_content(10 * 1024 * 1024):
                        fw.write(chunk)
                else:
                    return False
            seed = os.path.getsize(filepath)
            max_request_times -= 1

        logger.debug(f'下载路径: {filepath}')
        return True
