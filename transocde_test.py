# coding=utf-8
import logging
from utils.ffmpeg import ffprobe_get_media_info, process_audio

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
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
src = 'E:\www\www.bilibili.com\downloaded\Falcao_e_o_Soldado_Invernal.S01E06_WEB-DL_1080p_DUAL_5.1.COMANDO.TO.mkv'
output = 'test.tmp'
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
                # 只有aac, 通过aac生成这个语言的ac3
                need_get_ac3_list.append(has_aac_tuple[1])
            elif has_eac3_tuple[0] and not has_other_tuple[0]:
                # 除了aac, 只有eac3, 将eac3转换成aac, 并生成ac3
                # trans_aac_list.append(has_eac3_tuple[1])
                need_get_ac3_list.append(has_eac3_tuple[1])
            elif has_other_tuple[0] and not has_eac3_tuple[0]:
                # 除了aac, 只有其他类型, 转换成aac, 并生成ac3
                # trans_aac_list.append(has_other_tuple[1])
                need_get_ac3_list.append(has_other_tuple[1])
        elif has_ac3_tuple[0]:
            if not has_eac3_tuple[0] and not has_other_tuple[0]:
                # 只有ac3, 需要转换成aac, 并生成ac3
                trans_aac_list.append(has_ac3_tuple[1])
                need_get_ac3_list.append(has_ac3_tuple[1])
            elif has_eac3_tuple[0] and not has_other_tuple[0]:
                # 除了ac3, 只有eac3, 需要转换成aac, 并生成ac3
                trans_aac_list.append(has_eac3_tuple[1])
            # elif has_other_tuple[0] and not has_eac3_tuple[0]:
            #     # 除了ac3, 只有其他类型, 需要转换成aac
            #     trans_aac_list.append(has_other_tuple[1])
        else:
            # eac3和其他类型会被转换成aac, 需要生成ac3
            if not has_eac3_tuple[0]:
                need_get_ac3_list.append(has_other_tuple[1])
            else:
                need_get_ac3_list.append(has_eac3_tuple[1])

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
