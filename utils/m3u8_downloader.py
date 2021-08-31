# -*- coding: utf-8 -*-
# @Author      : LJQ
# @Time        : 2020/9/27 10:55
# @Version     : Python 3.6.4
__all__ = ['iqiyi_m3u8_download', 'IQIYIM3u8Download']

import logging.handlers
import shutil
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path

import requests
from Crypto.Cipher import AES
from func_timeout import FunctionTimedOut, func_set_timeout

log_path = Path(__file__).parent / 'log'
log_path.mkdir(parents=True, exist_ok=True)
handler_rotate = logging.handlers.TimedRotatingFileHandler(f"utils/log/{Path(__file__).stem}.log", when="D", interval=1,
                                                           encoding='utf-8', backupCount=3)
handler_rotate.setLevel(logging.INFO)
formatter = logging.Formatter(
    '[%(asctime)s %(filename)s][line:%(lineno)d] [%(process)d-%(threadName)s-%(thread)d:] %(levelname)-8s %(message)s')
handler_rotate.setFormatter(formatter)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] [%(process)d-%(threadName)s-%(thread)d:] %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d-%H:%M:%S',
                    handlers=[handler_rotate]
                    )

logger = logging.getLogger(__name__)


class TSFileException(Exception):
    """TS文件异常"""


class TSFileHeaderError(Exception):
    """TS文件头错误"""


def iqiyi_m3u8_download(urls: list, filepath: str, headers: dict = None, *, keys: list = None,
                        chunk_size: int = 1 * 1024 * 1024, wipe_cache: bool = True, thread_num: int = 10):
    try:
        with IQIYIM3u8Download(thread_num, headers) as imd:
            if urls:
                return imd.download(urls, filepath, keys=keys, chunk_size=chunk_size, wipe_cache=wipe_cache)
    except Exception as e:
        logger.exception(f'下载失败: {e}')
    return False, urls


def get_server_id():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        server_ip = s.getsockname()[0]
    finally:
        s.close()
    return server_ip


class IQIYIM3u8Download(object):

    server_ip = get_server_id()
    if server_ip == "185.233.185.81":
        TMP_DIR = Path('/home/www_202/tmp/m3u8/')
    else:
        TMP_DIR = Path('/home/www/tmp/m3u8/')

    def __init__(self, thread_num: int = 10, headers: dict = None):
        if thread_num < 1:
            thread_num = 1
        self.executor = ThreadPoolExecutor(max_workers=thread_num)
        self.headers = headers
        self.keys = dict()

    def deletedir(self, dirname: str):
        dirname = Path(dirname)
        # REMIND: 首次下载时清空文件夹，自动删除以前下载的文件
        if dirname.exists() and dirname.is_dir():
            for file in dirname.iterdir():
                file.unlink()
            dirname.rmdir()
            logger.warning(f'删除已存在文件夹: {dirname}')

    def control(self, urls: list, filepath: str, *, keys: list = None,
                chunk_size: int = 1 * 1024 * 1024, wipe_cache: bool = True):
        dirname = Path(filepath).parent
        filename = Path(filepath).name
        dirname_tmp = self.TMP_DIR / dirname.name / f"{filename}文件夹"
        self.deletedir(dirname_tmp)
        new_filepath = dirname_tmp / filename
        new_filepath.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f'创建文件夹: {dirname_tmp}')
        self._get_keys(set(keys))
        failures = self._threads_download(
            list(zip(range(1, len(urls) + 1), urls)), new_filepath, keys, chunk_size)
        for i in range(5):
            if failures:
                failures = self._threads_download(
                    failures, new_filepath, keys, chunk_size)
        if not failures:
            self._merge_files(dirname_tmp, filepath, wipe_cache)
        return not bool(failures), failures

    download = control

    def _get_keys(self, keys):
        logger.info(f'下载keys: {keys}')
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/85.0.4183.102 Safari/537.36'
        }
        if self.headers:
            headers = self.headers
        for key in keys:
            if key is None:
                continue
            for rt in range(10):
                try:
                    content = requests.get(key, headers=headers).content
                    self.keys[key] = AES.new(content, AES.MODE_CBC, content)
                except Exception as e:
                    if rt == 9:
                        raise e
                else:
                    break

    @staticmethod
    def _merge_files(dirname, filepath, wipe_cache):
        dirname = Path(dirname)
        filepath_tmp = dirname.parent / Path(filepath).name
        with suppress(Exception):
            Path(filepath_tmp).unlink()
            logger.info(f'删除已存在文件: {filepath_tmp}')
        logger.info(f'合并文件: {dirname} -> {filepath_tmp}')
        with open(filepath_tmp, 'ab') as fwb:
            for filename in sorted(dirname.iterdir()):
                fwb.write(filename.read_bytes())
                fwb.flush()
                if wipe_cache:
                    filename.unlink()
                    logger.debug(f'删除文件: {filename}')
        if wipe_cache:
            dirname.rmdir()
            logger.info(f'删除文件夹: {dirname}')
        shutil.move(filepath_tmp, filepath)
        logger.info(f'move {filepath_tmp} to {filepath}')

    @staticmethod
    def _get_seed(filepath):
        try:
            with open(filepath, mode='rb') as fr:
                seed = len(fr.read())
        except FileNotFoundError:
            seed = 0
        return seed

    def _threads_download(self, urls, filepath, keys, chunk_size):
        failures = []
        results = self.executor.map(self._download, urls, [
                                    filepath] * len(urls), keys, [chunk_size] * len(urls))
        for result in results:
            if result:
                failures.append(result)
        return failures

    def _download(self, url, filepath: str, key: str, chunk_size: int):
        all_files = [str(filename)
                     for filename in Path(filepath).parent.iterdir()]
        index, url = url
        success_path = f'{filepath}.{index:05}1'
        if success_path in all_files:
            logger.info(f'已存在: {success_path}')
            return
        failure_path = f'{filepath}.{index:05}0'
        try:
            self.__download(url, failure_path, key, chunk_size)
        except (requests.exceptions.RequestException, TSFileHeaderError, FunctionTimedOut) as e:
            logger.warning(f'下载失败: {url}, {index}, {str(e)}')
            return index, url
        except Exception as e:
            logger.exception(f'下载异常: {url}, {index}, {e}')
            raise e
        else:
            logger.debug(f'下载成功: {url}')
            Path(failure_path).rename(f'{failure_path[:-1]}1')

    @func_set_timeout(600)
    def __download(self, url: str, filepath: str, key: str, chunk_size: int):
        # TODO 2020-11-01 ts文件判断，单条链接数据处理
        # file_size = self._get_seed(filepath)
        headers = {
            # 'range': f'bytes={file_size}-',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/85.0.4183.102 Safari/537.36'
        }
        if self.headers:
            headers = self.headers

        with requests.session() as session:
            resp_bytes = session.request(
                'get', url, headers=headers, timeout=30).content
            # resp_bytes bytes长度满足16的倍数
            while True:
                if len(resp_bytes) % 16 != 0:
                    resp_bytes += b'0'
                else:
                    break
            with open(filepath, 'wb') as fwb:
                if key and self.keys:
                    resp_bytes = self.keys[key].decrypt(resp_bytes)
                file_header = b'G@'
                position = resp_bytes.find(file_header)
                logger.info(
                    f'position: {position}, filepath: {filepath}, content: {resp_bytes[:20]}, url: {url}')
                # print(f'position: {position}, filepath: {filepath}, content: {resp_bytes[:20]}, url: {url}')
                if position > -1:
                    resp_bytes = resp_bytes[position:]
                else:
                    raise TSFileHeaderError()
                fwb.write(resp_bytes)

    def close(self):
        self.executor.shutdown()
        return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
