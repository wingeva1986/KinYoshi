import sys
import time
import logging
import requests
from pathlib import Path

sys.path.append('.')
sys.path.append('..')
from utils.m3u8_downloader import IQIYIM3u8Download
from func_timeout import func_set_timeout, FunctionTimedOut
from tenacity import retry, stop_after_attempt, wait_fixed
from utils.util_agent import choice_agent

logger = logging.getLogger(__name__)


class TSFileException(Exception):
    """TS文件异常"""


class TSFileHeaderError(Exception):
    """TS文件头错误"""


def bde4_download(urls: list, filepath: str, headers: dict = None, *, keys: list = None,
                  chunk_size: int = 1 * 1024 * 1024, wipe_cache: bool = True, thread_num: int = 10):
    try:
        with Bde4Downloader(thread_num, headers) as imd:
            if urls:
                return imd.download(urls, filepath, keys=keys, chunk_size=chunk_size, wipe_cache=wipe_cache)
    except Exception as e:
        logger.exception(f'下载失败: {e}')
    return False, urls


class Bde4Downloader(IQIYIM3u8Download):
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
        for i in range(20):
            if failures:
                failures = self._threads_download(
                    failures, new_filepath, keys, chunk_size, sleep_time=2)
        if not failures:
            self._merge_files(dirname_tmp, filepath, wipe_cache)
        return not bool(failures), failures

    download = control

    def _threads_download(self, urls, filepath, keys, chunk_size, **kwargs):
        sleep_time = kwargs.get('sleep_time', 0)
        failures = []
        results = self.executor.map(self.downloader, urls, [
                                    filepath] * len(urls), keys, [chunk_size] * len(urls), [sleep_time] * len(urls))
        for result in results:
            if result:
                failures.append(result)
        return failures

    def downloader(self, url, filepath: str, key: str, chunk_size: int, sleep_time: int):
        all_files = [str(filename)
                     for filename in Path(filepath).parent.iterdir()]
        index, url = url
        success_path = f'{filepath}.{index:05}1'
        if success_path in all_files:
            logger.info(f'已存在: {success_path}')
            return
        failure_path = f'{filepath}.{index:05}0'
        try:
            self.__download(url, failure_path, key, chunk_size, sleep_time)
        except (requests.exceptions.RequestException, TSFileHeaderError, FunctionTimedOut) as e:
            # logger.warning(f'下载失败: {url}, {index}, {str(e)}')
            print(f'下载失败: {url}, {index}, {str(e)}')
            return index, url
        except Exception as e:
            # logger.exception(f'下载异常: {url}, {index}, {e}')
            print(f'下载异常: {url}, {index}, {e}')
            raise e
        else:
            logger.debug(f'下载成功: {url}')
            Path(failure_path).rename(f'{failure_path[:-1]}1')

    @func_set_timeout(600)
    def __download(self, url: str, filepath: str, key: str, chunk_size: int, sleep_time: int):
        # TODO 2020-11-01 ts文件判断，单条链接数据处理
        # file_size = self._get_seed(filepath)
        headers = {'user-agent': choice_agent()}
        if self.headers:
            headers = self.headers
        if sleep_time:
            time.sleep(sleep_time)

        with requests.session() as session:
            resp_bytes = session.request(
                'get', url, headers=headers, timeout=120, verify=False).content
            with open(filepath, 'wb') as fwb:
                if key and self.keys:
                    resp_bytes = self.keys[key].decrypt(resp_bytes)
                file_header = b'G@'
                position = resp_bytes.find(file_header)
                logger.info(
                    f'position: {position}, filepath: {filepath}, content: {resp_bytes[:20]}, url: {url}')
                if position > -1:
                    resp_bytes = resp_bytes[position:]
                else:
                    raise TSFileHeaderError()
                fwb.write(resp_bytes)
