import json
import sys
import os
import zlib
from abc import ABCMeta, abstractmethod
from contextlib import suppress
from pathlib import Path
import eventlet
import m3u8
import logging
import requests
sys.path.append('.')
sys.path.append('..')

from utils.bilibli_parse import BiLiBiLi
from utils.several_mp4s_downloader import several_mp4s_download
from utils.advanced_audio_coding import AAC
from utils.several_urls_downloader import several_urls_download
from utils.single_mp4_downloader import single_mp4_download
from utils.m3u8_downloader import iqiyi_m3u8_download
from utils.util_agent import choice_agent
from utils.CommonUtils import header_list_to_dic, get_header_list


logger = logging.getLogger(__name__)


def parse_m3u8_url(url: str, headers: dict):
    content = ''
    try:
        response = requests.get(url, headers=headers, allow_redirects=False)
        if response.status_code == 200:
            content = response.text
        elif response.status_code == 302:
            real_m3u8_url = response.headers['Location']
            response = requests.get(real_m3u8_url, headers=headers)
            content = response.text
            if not content.startswith('#EXTM3U'):
                content = zlib.decompress(response.content[3354:], 16 + zlib.MAX_WBITS).decode('utf-8')
    except BaseException as e:
        logger.warning(f'parse m3u8 url error {e}')
    return content



class M3u8Downloader():
    def download(self, url, output, **kwargs):
        logger.info('download url %s', url)
        headers = kwargs.get('headers', {})
        provider = kwargs.get('provider', {})
        if isinstance(headers, list):
            headers = header_list_to_dic(headers)
        elif isinstance(headers, dict):
            headers = headers
        headers = {'User-Agent': choice_agent()} if not headers else headers
        logger.info('headers -> %s', headers)

        output_dir = '\\'.join(output.split('\\')[:-1])
        logger.info('download %s output_dir=%s', output, output_dir)
        if url.startswith('http'):
            content = parse_m3u8_url(url, headers)
            m3u8_obj = m3u8.loads(content)
        else:
            # m3u8 提取uri和key
            m3u8_obj = m3u8.loads(url)
        urls = m3u8_obj.segments.uri

        if not not urls:
            if not str(urls[0]).startswith('http'):
                position = url.find('.m3u8')
                prefix_url = '/'.join(url[:position].split('/')[:-1])
                urls = [f'{prefix_url}/{url}' for url in urls]
        keys = [key.uri for key in m3u8_obj.keys if key]
        if len(keys) < 2:
            key = keys and keys[0] or None
            keys = [key for _ in range(len(urls))]
        if len(keys) != len(urls):
            logger.info('ts downloaded result=False')
            return False
        eventlet.monkey_patch()
        download_res, _ = iqiyi_m3u8_download(urls, output, headers=headers, keys=keys, thread_num=5)
        logger.info('ts downloaded result=%s', download_res)


class BiLiBiLiDownloader():
    def download(self, url, output, **kwargs):
        logger.info('download url %s', url)
        headers = kwargs.get('header', {})
        if isinstance(headers, list):
            headers = header_list_to_dic(headers)
        elif isinstance(headers, dict):
            headers = headers
        headers = {'User-Agent': choice_agent()} if not headers else headers
        logger.info('headers -> %s', headers)

        output_dir = '\\'.join(output.split('\\')[:-1])
        logger.info('download %s output_dir=%s', output, output_dir)

        video_url = url['video_url']
        audio_url = url['audio_url']
        video_output = output + '.video.tmp'
        audio_output = output + '.audio.tmp'
        download_res = single_mp4_download(video_url, video_output, headers=headers)
        if download_res:
            download_res = single_mp4_download(audio_url, audio_output, headers=headers)
        if download_res:
            mp4_output = output + '.video.mp4'
            command = f'ffmpeg -i "{video_output}" -i "{audio_output}" -codec copy "{mp4_output}" -safe 0'
            logger.info(f'ffmpeg 音视频合成 mp4 文件: {output}\n{command}')
            download_res = not os.system(command)
            if download_res:
                Path(mp4_output).rename(output)
                logger.info(f'mp4 文件重命名: {mp4_output} -> {output}')
                Path(video_output).unlink()
                Path(audio_output).unlink()
        logger.info('ts downloaded result=%s', download_res)
        return download_res


class SeveralMp4sDownloader():
    def download(self, url, output, **kwargs):
        vinfo = kwargs['vinfo']
        url = url or vinfo.get('urls') or vinfo.get('url')
        logger.info('download url %s', url)
        headers = kwargs.get('headers', {}) or vinfo.get('headers')
        if isinstance(headers, list):
            headers = header_list_to_dic(headers)
        elif isinstance(headers, dict):
            headers = headers
        headers = {'User-Agent': choice_agent()} if not headers else headers
        logger.info('headers -> %s', headers)

        output_dir = '\\'.join(output.split('\\')[:-1])
        logger.info('download %s output_dir=%s', output, output_dir)
        download_res, _ = several_mp4s_download(url, output, headers=headers)
        logger.info('ts downloaded result=%s', download_res)
        return download_res


class IAudios(metaclass=ABCMeta):
    """
    音频校正接口
    """

    @abstractmethod
    def adjust(self, filepath: str, **kwargs: dict) -> bool:
        """
        校正音频内容

        Args:
            filepath: 音频路径
            **kwargs:

        Returns: 是否校正成功

        """


class DefaultAudios(IAudios):
    """
    默认音频校正
    """

    def adjust(self, filepath: str, **kwargs: dict) -> bool:
        """无需校正"""
        return True


class IQIYIAudios(IAudios):
    """
    iQIYI 音频校正
    """

    def adjust(self, filepath: str, **kwargs: dict) -> bool:
        """音频解码"""
        with open(filepath, 'rb') as fr:
            content = fr.read()
        index = content.find(b'mdat')
        tmp_filepath = filepath.strip('.tmp') + '.slice.tmp'
        if index <= -1:
            index = -4
        with open(tmp_filepath, 'wb') as fw:
            fw.write(content[index + 4:])
        output_filepath = tmp_filepath.strip('.slice.tmp') + '.renovate.tmp'
        is_renovate = AAC.renovate(tmp_filepath, output_filepath)
        with suppress(Exception):
            Path(tmp_filepath).unlink()
        if is_renovate:
            with suppress(Exception):
                Path(filepath).unlink()
            Path(output_filepath).rename(filepath)
        else:
            with suppress(Exception):
                Path(output_filepath).unlink()

        logger.warning(f'is_renovate: {is_renovate}')
        return is_renovate


def audio_factory(provider: str, **kwargs: dict) -> IAudios:
    """
    音频校正工厂
    Args:
        provider: 提供商
        **kwargs:

    Returns:

    """
    if provider == 'www.iqiyi.com.auto':
        return IQIYIAudios()
    return DefaultAudios()


class AudiosVideoMergeDownloader():

    def download(self, url, output, **kwargs):
        provider = kwargs.get('provider', '')
        vinfo = kwargs.get('vinfo') or {}
        logger.info(f'vinfo: {vinfo}')
        audios = vinfo.get('audios') or []
        video = vinfo.get('video') or {}
        video_type = video.get('type')
        thread_num = kwargs.get('thread_num', 10)

        output_dir = '\\'.join(output.split('\\')[:-1])
        logger.info('download %s output_dir=%s', output, output_dir)
        download_res = True

        # 音频下载
        audio_paths = []
        video_paths = []
        for index, audio in enumerate(audios):
            audio_output = output.strip('.tmp') + f'.{index}.audio.tmp'
            audio_paths.append(audio_output)
            urls = audio['urls']
            headers = audio['headers']
            download_res, _ = several_urls_download(urls, audio_output, headers=headers, thread_num=thread_num)
            if download_res:
                download_res = audio_factory(provider).adjust(audio_output)
            if not download_res:
                break

        if download_res:
            # 视频下载
            video_output = str(Path(output).parent / ('video' + Path(output).name))
            video_paths.append(video_output)
            urls = video['urls']
            headers = video['headers']
            if video_type == 'several_mp4s_download':
                download_res, _ = several_mp4s_download(urls, video_output, headers=headers)
            else:
                keys = [None] * len(urls)
                download_res, _ = iqiyi_m3u8_download(urls, video_output, headers=headers, keys=keys,
                                                      thread_num=thread_num)
            if download_res:
                # 添加多个音频到视频中
                for index, audio_output in enumerate(audio_paths):
                    tmp_output = video_output.strip('.tmp') + f'.{index}.tmp'
                    command = f'ffmpeg -i "{video_output}" -i "{audio_output}" -map 0 -map 1:a -c copy -f mpegts -y "{tmp_output}" -safe 0'
                    video_output = tmp_output
                    video_paths.append(video_output)
                    logger.info(f'ffmpeg 音视频合成视频文件: {output}\n{command}')
                    download_res = not os.system(command)
                    if not download_res:
                        break
            if download_res:
                Path(video_output).rename(output)
                logger.info(f'视频文件重命名: {video_output} -> {output}')
                for video_output in video_paths:
                    with suppress(Exception):
                        Path(video_output).unlink()
                for audio_output in audio_paths:
                    with suppress(Exception):
                        Path(audio_output).unlink()
        logger.info('ts downloaded result=%s', download_res)
        return download_res


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    url = f'https://www.bilibili.com/bangumi/play/ep412068'
    output = f'E:\\YunBo\\开挂药师的奇幻世界悠闲生活.s1e8.162991439580179660.mp4'

    res = BiLiBiLi(url).parse()
    data = json.dumps(res)
    print(data)
    vinfo = res[0]['vinfo']
    down_type = vinfo['type']

    if down_type == 'several_mp4s_download':
        url = vinfo['urls']
        headers = vinfo['headers']
        donwload_res = SeveralMp4sDownloader().download(url, output, headers=headers, keys=[], provider='', vinfo=res[0]['vinfo'])
    else:
        url = ''
        donwload_res = AudiosVideoMergeDownloader().download(url, output, vinfo=vinfo)
    print(res)
