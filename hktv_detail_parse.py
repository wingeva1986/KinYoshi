# coding=utf-8
from os import extsep
import re
import time
import requests
from scrapy import Selector, selector
from utils.util_agent import choice_agent
from utils.CommonUtils import trans_to_alb

def get_filter_keys(file_path):
    filter_list = []
    try:
        with open(file_path, encoding='utf-8') as f:
            filter_list = f.read().split('\n')
    except BaseException as e:
        print(e)
    return filter_list

def detail_page(response, name, **kwargs):
    def choose_tuple_episode(ep_names: tuple):
        return [i for i in ep_names if i]
    year = kwargs.get('year', '')
    now_year = str(int(time.strftime("%Y")))
    download_list, download_urls = [], []
    uppercase_number_str = '|'.join(['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '百', '千'])
    uppercase_number_pattern = re.compile(f'([{uppercase_number_str}]+)集')
    zongyi_pattern = re.compile('|'.join([r'([0-9\-]{10})[期（）上下]*', r'([0-9\-]{8})[期（）上下]*', r'([0-9\-]{6})[期（）上下]*', r'([0-9\-]{4})[期（）上下]*']))
    tv_dont_need_pattern = re.compile('|'.join([r'蓝光', r'[a-zA-Z]+[高清国粤语]*', r'1080[pP]+', r'\d+资源', r'演唱会', r'高清', r'标清']))
    tv_seq_num_pattern = re.compile('|'.join([r'\d+', r'\d+集', f'[{uppercase_number_str}]+集']))
    video_type = response.xpath('//li[@class=" active hidden-sm hidden-xs"]/a/text()').get()
    
    play_info_list = response.xpath('//div[@class="myui-panel myui-panel-bg clearfix"]/div/div[2]/ul[@class="myui-content__list scrollbar sort-list clearfix"]')
    for play_info in play_info_list:
        result_list = []
        url_names = play_info.xpath('li/a/text()').getall()
        play_urls = play_info.xpath('li/a/@href').getall()
        
        if len(url_names) == len(play_urls):
            for i in range(len(url_names)):
                if play_urls[i] and url_names[i] and '预告' not in url_names[i]:
                    play_url = 'https://www.hktv03.com' + play_urls[i] if not play_urls[i].startswith('http') else play_urls[i]
                    url_name = url_names[i]
                    episode_name = ''
                    if video_type.find('电影') >= 0:
                        if zongyi_pattern.search(url_name):
                            continue
                        episode_name = name
                    elif video_type.find('电视剧') >= 0:
                        if tv_seq_num_pattern.search(url_name):
                            if uppercase_number_pattern.search(url_name):
                                upper_seq_num = uppercase_number_pattern.search(url_name).group(1)
                                episode_name = trans_to_alb(upper_seq_num)
                            else:
                                episode_name = re.findall(r'(\d+)', url_name)[0]
                            episode_name = str(int(episode_name))
                    elif video_type.find('综艺') >= 0:
                        if zongyi_pattern.search(url_name):
                            ep_name_tuple = re.findall(zongyi_pattern, url_name)[0]
                            episode_name = choose_tuple_episode(ep_name_tuple)[0]
                            if '上' in url_name:
                                episode_name = episode_name + '上'
                            if '下' in url_name:
                                episode_name = episode_name + '下'
                            episode_name = episode_name.replace('-', '')
                            if len(episode_name) == 6:
                                episode_name = now_year[:2] + episode_name if not year else year + episode_name
                            if len(episode_name) == 4:
                                episode_name = now_year + episode_name if not year else year + episode_name
                if play_url and episode_name:
                    result_list.append({
                        'name': name,
                        'url': [play_url],
                        'episode_name': episode_name
                    })
        download_list.append(result_list)
    
    two_part_channel_index = []
    if video_type.find('综艺') >= 0:
        for i in range(len(download_list)):
            if [j['episode_name'] for j in download_list[i]if re.compile(r'[上下]+').search(j['episode_name'])]:
                two_part_channel_index.append(i)
    
    if two_part_channel_index:
        for i in two_part_channel_index:
            for j in download_list[i]:
                download_urls.append(j)
    else:
        for i in download_list:
            for j in i:
                download_urls.append(j)

    for i in download_urls:
        print(i)
        # url = 'https://www.hktv03.com' + str(play_url) if play_url else ''
        # if (url_name and '预告' in url_name) or not url_name:
        #     continue
        # if not url:
        #     continue
        # download_url['url'].append(url)
        # download_url['name'] = name
        # if video_type == '[1]电影':
        #     pattern = re.compile(r'([0-9\-]{10}|[0-9\-]{8}|[0-9\-]{6})')
        #     if '期' in url_name or '上期' in url_name or pattern.search(url_name) or '第' in url_name or '集' in url_name:
        #         continue
        #     download_url['episode_name'] = name
        # elif video_type == '[2]电视剧':
        #     pattern = re.compile(r'([0-9\-]{10}|[0-9\-]{8}|[0-9\-]{6})')
        #     if '期' in url_name or '上期' in url_name or '下期' in url_name or pattern.search(url_name):
        #         continue
        #     if url_name == '蓝光' or url_name == 'HD高清' or url_name == '高清' or url_name == '1080P' or url_name == '1080p' or url_name == '8090资源' or url_name == 'HD国语' or url_name == 'HD粤语' or url_name == '演唱会':
        #         continue
        #     if '粤语' in name:
        #         if '国语' in url_name:
        #             continue
        #     if '国语' in name:
        #         if '粤语' in url_name:
        #             continue
        #     download_url['episode_name'] = url_name
        # elif video_type == '[6]综艺':
        #     pattern = re.compile(r'([0-9\-]{10}|[0-9\-]{8}|[0-9\-]{6})')
        #     if not pattern.search(url_name) or '陪看版' in url_name or re.compile(r'期\-\d+').search(url_name):
        #         continue
        #     last_episode_name = re.findall(
        #         r'([0-9\-]+|[0-9\-]+)', str(url_name))[0]
        #     if '-' in last_episode_name:
        #         last_episode_name = ''.join(last_episode_name.split('-'))
        #     if len(last_episode_name) == 6:
        #         now_year = f'{int(time.strftime("%Y")) - 1}'
        #         last_episode_name = f'{now_year[:2]}{last_episode_name}'
        #     # if '上' in url_name or '上期' in url_name:
        #     #     last_episode_name = f'{last_episode_name}上'
        #     # if '下' in url_name or '下期' in url_name:
        #     #     last_episode_name = f'{last_episode_name}下'
        #     download_url['episode_name'] = last_episode_name
        # elif video_type == '[8]动漫':
        #     download_url['episode_name'] = url_name

        # if video_type != '[6]综艺':
        #     episode = 0
        #     try:
        #         try:
        #             # 将01-09改成1-9
        #             episode = num_reduce_zore(re.findall(
        #                 r'(\d+)集', str(download_url['episode_name']))[0])
        #             download_url['episode_name'] = episode
        #         except:
        #             episode = re.findall(
        #                 r'(\d+)集', str(download_url['episode_name']))[0]
        #             download_url['episode_name'] = episode
        #     except:
        #         if item['video_type'] == '[2]电视剧':
        #             try:
        #                 episode = re.findall(
        #                     r'(\d+)', str(download_url['episode_name']))[0]
        #                 download_url['episode_name'] = episode
        #             except:
        #                 pass
        #         else:
        #             # 如果无法获取到就从url中获取集数
        #             episode = re.findall(
        #                 r'(\d+)', str(download_url['url'][0].split('/')[-1]))[0]
        #             download_url['episode_name'] = episode
        # download_list.append(download_url)



if __name__ == '__main__':
    url = 'https://www.hktv03.com/vod/detail/id/4335.html'
    headers = {'User-Agent': choice_agent()}
    response = requests.get(url, headers=headers)
    selector = Selector(text=response.text)
    detail_page(selector, '良心')
    # filter_keys_path = './filter_keys.txt'
    # filter_keys = get_filter_keys(filter_keys_path)

    # uppercase_number_str = '|'.join(['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '百', '千'])
    # zongyi_pattern = re.compile('|'.join([r'([0-9\-]{10})[期（）上下]*', r'([0-9\-]{8})[期（）上下]*', r'([0-9\-]{6})[期（）上下]*', r'([0-9\-]{4})[期（）上下]*']))
    # tv_dont_need_pattern = re.compile('|'.join([r'蓝光', r'[a-zA-Z]+[高清国粤语]*', r'1080[pP]+', r'\d+资源', r'演唱会', r'高清', r'标清']))
    # tv_seq_num_pattern = re.compile('|'.join([r'\d+', r'\d+集', f'[{uppercase_number_str}]+集']))
    # print(zongyi_pattern.search('0748'))

    
