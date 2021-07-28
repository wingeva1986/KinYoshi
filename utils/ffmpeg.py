import shutil
import subprocess
import os
import re
import json
import logging
import chardet

import time
import traceback
import platform

logger = logging.getLogger(__name__)

UNKNOW_SIZE = -1.0
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
'''
转码算法：
1.视频处理：
    1.1. 默认copy_mode, 如果视频不是h264或h265, 则需要transcode. 如果有外挂.idx/.sub字幕也需要transcode
    1.2. 转码模式下:
        1.2.1. 有GPU但是码率不大, 则直接copy
        1.2.2. 有GPU但是码率过大, 则转成h265
        1.2.3. 没有GPU, 则转成h264
2.音频处理：
    2.1 当只有ac3音轨或者有其他音轨的时候,需要转成aac, 再生成ac3
    2.2 当只有aac和ac3是无需再生成ac3
    aac: 声道为立体声, 原码率小于128修改为128, 大于128小于400修改为192, 大于400修改为320
    ac3: 原本是两声道的话码率为192, 大于等于六声道修改为六声道码率为320, 声道数不知道则为六声道码率为320
3.字幕处理：
    3.1 外挂字幕.srt  使用 -vf subtitles="sub.srt"
    3.2 外挂字幕.sub/.idx 使用 -filter_complex "[0:V][1:s:x]overlay=0:H-h" ，需实现根根据语言选择字幕
        3.2.1 无指定语言时优先en 使用-filter_complex "[0:V][1:s:x]overlay=0:H-h"
        3.2.2 无en则默认选择langidx 使用-filter_complex "[0:V][1:s]overlay=0:H-h"
    3.3 内置字幕导出到外部字幕，同外部字幕相同处理 ，ffmpeg -i xxx.mkv -map 0:3 xxx.srt ，需实现根据语言选择导出字幕
        3.3.1 内置字幕无指定语言时优先eng 
        3.3.2 内置字幕无eng则默认选择第一个语言 ffmpeg -i xxx.mkv -map 0:s:0 xxx.srt
'''

'''
ffmpeg处理音频:
测试文件: media_toolset/transocder_test_filie
1. 已有aac并且只有aac, copy aac音轨并添加ac3音轨
    Stream #0:1 aac 66k     码率小于400k, 无需转
    Stream #0:2 aac 66k     码率小于400k, 无需转
    ffmpeg -i video_aac_aac.ts -map 0:1 -vn -acodec copy -f mp4 -y aac_1.ts
    ffmpeg -i video_aac_aac.ts -map 0:2 -vn -acodec copy -f mp4 -y aac_2.ts
    ffmpeg -i video_aac_aac.ts -map 0:1 -map 0:2 -vn -acodec ac3 -ab 192k -ac 6 -f mp4 -y ac3.ts
2. 有aac和ac3, aac码率小于400k直接copy aac, ac3码率大于于400k, 需要转成320k
    Stream #0:1 aac 66k     码率小于400k, 无需转
    Stream #0:1 ac3 448k    码率大于于400k, 需要转成320k
    ffmpeg -i video_aac_ac3.ts -map 0:1 -vn -acodec copy -f mp4 -y aac_1.ts
    ffmpeg -i video_aac_ac3.ts -map 0:2 -vn -acodec ac3 -ab 320k -f mp4 -y ac3_2.ts
3. 只有ac3(包含eac3), 都需要先将ac3/eac3转成aac, 再添加dolby音轨
    Stream #0:1 ac3 448k    码率大于于400k, 需要转成320k
    Stream #0:2 ac3 448k    码率大于于400k, 需要转成320k
    ffmpeg -i video_ac3_ac3.ts -map 0:1 -vn -acodec aac -ab 320k -f mp4 -y aac_1.ts
    ffmpeg -i video_ac3_ac3.ts -map 0:2 -vn -acodec aac -ab 320k -f mp4 -y aac_2.ts
    ffmpeg -i video_ac3_ac3.ts -map 0:1 -map 0:2 -vn -acodec ac3 -ab 192k -ac 6 -f mp4 -y ac3.ts
4. 当存在其他音轨时, 需要转成aac
    Stream #0:1 aac 57k     码率小于400k, 无需转
    Stream #0:2 aac 57k     码率小于400k, 无需转
    Stream #0:3 dts 1411k   码率大于400k, 需要转成320k
    ffmpeg -i video_aac_aac_dts.ts -map 0:1 -vn -acodec copy -f mp4 -y aac_1.ts
    ffmpeg -i video_aac_aac_dts.ts -map 0:2 -vn -acodec copy -f mp4 -y aac_2.ts
    ffmpeg -i video_aac_aac_dts.ts -map 0:3 -vn -acodec aac -ab 320k -f mp4 -y aac_3.ts
    ffmpeg -i video_aac_aac_dts.ts -map 0:1 -map 0:2 -map 0:3 -vn -acodec ac3 -ab 192k -ac 6 -f mp4 -y ac3.ts
5. 混合例子, 包含ac3和aac的大码率和小码率
    Stream #0:1 ac3 448k    码率大于于400k, 需要转成320k
    Stream #0:2 ac3 192k    码率小于400k, 无需转
    Stream #0:3 ac3 640k    码率大于于400k, 需要转成320k
    Stream #0:4 aac 318k    码率小于400k, 无需转
    Stream #0:5 aac 405k    码率大于于400k, 需要转成320k
    ffmpeg -i video_have_big_rate_audio.ts -map 0:1 -vn -acodec ac3 -ab 320k -f mp4 -y ac3_1.ts
    ffmpeg -i video_have_big_rate_audio.ts -map 0:2 -vn -acodec copy -f mp4 -y ac3_2.ts
    ffmpeg -i video_have_big_rate_audio.ts -map 0:3 -vn -acodec ac3 -ab 320k -f mp4 -y ac3_3.ts
    ffmpeg -i video_have_big_rate_audio.ts -map 0:4 -vn -acodec copy -f mp4 -y aac_4.ts
    ffmpeg -i video_have_big_rate_audio.ts -map 0:4 -vn -acodec aac -ab 320k -f mp4 -y aac_5.ts
6. 当音轨的声道数大于6时, 需要改成6声道
    Stream #0:1 aac 66k   channels 8   码率小于400k, 无需转, 声道数大于6, 需要改成6声道
    Stream #0:1 ac3 448k  channels 6   码率大于于400k, 需要转成320k
    ffmpeg -i video_aac_ac3_8c.ts -map 0:1 -vn -acodec aac -ac 6 -f mp4 -y aac_1.ts
    ffmpeg -i video_aac_ac3_8c.ts -map 0:2 -vn -acodec ac3 -ab 320k -f mp4 -y ac3_2.ts
'''

'''
ffmpeg提取字幕：
提取所有字幕 ffmpeg -i xxx.mkv -map 0:s -c copy default xxx_sub1.mkv
提取所有字幕 ffmpeg -i xxx.mkv -map 0:s -c copy -disposition:s:6 default xxx_sub1.mkv
提取指定字幕 ffmpeg -i xxx.mkv -map 0:s:0 sub1.srt 提取xxx.mkv中第一个字幕到sub1.srt文件
提取指定字幕 ffmpeg -i xxx.mkv -map 0:3 sub1.srt 提取xxx.mkv中第三个流到sub1.srt文件

ffmepeg 添加.srt字幕到视频中 mode 2:
ffmpeg -i  Tomb.mkv  -map 0:V:?  -map 0:a -c:v hevc_nvenc -max_muxing_queue_size 700 -preset fast -b:v 1300k -c:a aac -b:a 128k -metadata title="" -metadata author="" -metadata copyright="" -metadata comment="" -metadata description="" -vf subtitles=Tomb.srt  -vbsf hevc_mp4toannexb -f mpegts  -y Tomb.ts

ffmepeg将video.mkv中的字幕（默认）嵌入到out.avi文件
ffmpeg -i video.mkv -vf subtitles=video.mkv out.avi
eg:
ffmpeg -i  Tomb.mkv  -map 0:V:?  -map 0:a -c:v hevc_nvenc -max_muxing_queue_size 700 -preset fast -b:v 1300k -c:a aac -b:a 128k -metadata title="" -metadata author="" -metadata copyright="" -metadata comment="" -metadata description="" -vf subtitles=Tomb.mkv -vbsf hevc_mp4toannexb -f mpegts  -y Tomb.ts

ffmepeg 将某容器第二个字幕流合成到另一个容器的视频流中输出 mode 3：
ffmpeg -i input.mkv -vf subtitles=video.mkv:si=1 output.mkv
eg:
ffmpeg -i  Tomb.mkv  -map 0:V:?  -map 0:a -c:v hevc_nvenc -max_muxing_queue_size 700 -preset fast -b:v 1300k -c:a aac -b:a 128k -metadata title="" -metadata author="" -metadata copyright="" -metadata comment="" -metadata description="" -vf subtitles="Tomb.mkv:si=1" -vbsf hevc_mp4toannexb -f mpegts  -y Tomb.ts

ffmpeg添加 sub/idx格式字幕到视频中  mode 1：
ffmpeg -i "American.mp4" -i "American.idx" -i "American.sub" -map 0:V:?  -map 0:a -c:v hevc_nvenc -max_muxing_queue_size 700 -preset fast -b:v 1500k -c:a aac -b:a 128k -metadata title="" -metadata author="" -metadata copyright="" -metadata comment="" -metadata description="" -filter_complex "[0:V][1:s:4]overlay=0:H-h" -vbsf hevc_mp4toannexb  -f mpegts  -y American.ts

这条命令是加载American.mp4,American.idx,American.sub文件，然后通过滤镜将American.idx中index=4的字幕烧录进视频文件
其中：
    [0:V]指的第一个加载的视频文件American.MP4
    [1:s:4]指的是加载的American.idx文件，因为输入文件的索引是1,且选择该文件中的index=4的字幕数据
    overlay=0:H-h将字幕显示在视频下方。

此处使用的American.idx中语言index信息如下：
# VobSub index file, v7 (do not modify this line!)
# Language index in use
id: en, index: 0
id: fr, index: 1
id: es, index: 2
id: es, index: 3
id: pt, index: 4
id: pt, index: 5
id: it, index: 6
id: de, index: 7
id: nl, index: 8
id: sv, index: 9
id: no, index: 10
id: da, index: 11
id: fi, index: 12
id: ru, index: 13
id: cs, index: 14
id: pl, index: 15
id: hu, index: 16
id: el, index: 17
id: ja, index: 18
id: zh, index: 19
id: zh, index: 20
id: ko, index: 21
id: de, index: 22
'''


def get_srt_subtitle_file(name):
    video_name_without_ext = os.path.splitext(name)[0]

    srt_name = video_name_without_ext + '.srt'
    if os.path.exists(srt_name):
        logger.info("%s,%s", get_srt_subtitle_file, srt_name)
        return srt_name
    srt_name = video_name_without_ext + '.SRT'
    if os.path.exists(srt_name):
        logger.info("%s,%s", get_srt_subtitle_file, srt_name)
        return srt_name

    return None


'''
外挂字幕.sub/.idx 使用 -filter_complex "[0:V][1:s:x]overlay=0:H-h" ，
需实现根根据语言选择字幕
        3.2.1 无指定语言时优先en 使用-filter_complex "[0:V][1:s:x]overlay=0:H-h"
        3.2.2 无en则默认选择langidx 使用-filter_complex "[0:V][1:s]overlay=0:H-h"
target_lang：Language family,ISO 639-1 ,two letters ,eg: pt zh en
    target_lang={'iso639_1':'en','iso639_2':'eng'}
return:
    target_idx 字幕文件中根据语言选择index，返回-1则说明无对应的外挂字幕，其他值则可被用于[1:s:x]overlay=0:H-h的x
    target_idx_file .idx file path
    target_sub_file .sub file path
'''


def get_sub_idx_subtitle_file(name, target_lang, only_get_file=False):
    video_name_without_ext = os.path.splitext(name)[0]
    logger.info("%s,%s", video_name_without_ext, name)
    if isinstance(target_lang, dict):
        target_lang = target_lang['iso639_1']
    target_idx = -1
    target_idx_file = None
    target_sub_file = None
    idx_name = video_name_without_ext + '.idx'
    if os.path.exists(idx_name):
        target_idx_file = idx_name
    idx_name = video_name_without_ext + '.IDX'
    if os.path.exists(idx_name):
        target_idx_file = idx_name

    sub_name = video_name_without_ext + '.sub'
    if os.path.exists(sub_name):
        target_sub_file = sub_name
    sub_name = video_name_without_ext + '.SUB'
    if os.path.exists(sub_name):
        target_sub_file = sub_name
    if not target_idx_file or not target_sub_file:
        target_idx_file = None
        target_sub_file = None
        target_idx = -1
    else:
        if not only_get_file:
            subtitles = []
            for line in open(target_idx_file):
                # print line,  #python2 用法
                if line.startswith('id:'):
                    logger.info('%s', line.strip('\n'))
                    match = re.match(r'\s*id:\s*(\D*),\s*index\s*:\s*(\d*)\s*', line)
                    if not not match:
                        subtitle = {}
                        subtitle['lang'] = match.group(1)
                        subtitle['index'] = int(match.group(2))
                        subtitles.append(subtitle)
                        if subtitle['lang'] == target_lang:
                            target_idx = subtitle['index']
                            break
            if target_idx < 0:
                for subtitle in subtitles:
                    if subtitle['lang'] == 'en':
                        target_idx = subtitle['index']
        if target_idx < 0:
            target_idx = 0
    logger.info('get_sub_idx_subtitle_file {},{},{}'.format(target_idx, target_idx_file, target_sub_file))
    return target_idx, target_idx_file, target_sub_file


def __build_params(pub_params: list, last_param):
    os_type = platform.system()
    if os_type.startswith('Windows'):
        params = pub_params
        params.append("{last_param}".format(last_param=last_param))
        shell = False
    else:
        params = [' '.join(pub_params) + ' "{last_param}"'.format(last_param=last_param)]
        shell = True
    print(params)
    # print(shell)
    return shell, params


def ffmpeg_audio_tracks_process(input_file, output_file, track_list: list, shell, bit_rate=320, timeout=7200,
                                channels=2, **kwargs):
    '''
    :param input_file: input file
    :param output_file: target output file
    :param track_list: need process audio track
    :param shell: whether is shell
    :param bit_rate: target bit_rate
    :param timeout: maximum timeout setting
    :param channels: channel number
    :param kwargs:
    :return:
    '''
    ret = True
    target_codec = kwargs.get('target_codec', 'aac')
    trans_options = []
    for track_index in track_list:
        trans_options.append('-map')
        trans_options.append(f'0:{track_index}')
    trans_options += ["-vn", "-acodec", f"{target_codec}", "-ab", f"{bit_rate}"]
    trans_options += ["-ac", f'{channels}', "-ar", "44100", "-max_muxing_queue_size", "1500"]
    if not shell:
        cmd = ['ffmpeg', '-i', input_file] + trans_options + ['-f', 'mpegts', '-y', output_file]
    else:
        trans_options = ' '.join(trans_options)
        cmd = 'ffmpeg -i "%s" %s -f mpegts -y %s' % (input_file, trans_options, output_file)
    logger.info(f'trans audio tracks cmd={cmd}')
    try:
        subprocess.check_output(cmd, shell=shell, stdin=None, stderr=subprocess.STDOUT, timeout=timeout)
    except BaseException as e:
        ret = False
        logger.warning('transcode audio tracks failed %s params=[%s]\n %s', e, cmd, ' '.join(cmd))
        logger.warning(f'{traceback.print_exc()}')
    return ret


def gen_ac3_audio(input_file, output_file, all_ac3_list, audio_index_list, shell, add_dolby=True):
    ret = True
    if add_dolby and (all_ac3_list or audio_index_list):
        transcode_options = ["-vn", "-acodec", "ac3", "-ab", "320k", "-ac", "6"]
        if all_ac3_list:
            ac3_list = list(all_ac3_list)
        else:
            ac3_list = list(audio_index_list)

        '''
         we add all ac3 channels for the 
         1 gen output_ac3_tmp for ac3 channels,transcode eac3 to ac3
         2 combine output_tmp and output_ac3_tmp to output_full_name
         3 remove output_tmp and output_ac3_tmp
        '''
        # ffmpeg -i input.mp4 -vn -acodec ac3 -ab 384k -y output.mp4
        ac3_options = []
        for ac3_index in ac3_list:
            ac3_options.append('-map')
            ac3_options.append(f'0:{ac3_index}')
        ac3_options += transcode_options
        ac3_options += ["-ar", "48000", "-max_muxing_queue_size", "1500", "-f", "mp4", "-y"]
        if not shell:
            cmd = ['ffmpeg', '-i', input_file] + ac3_options + [output_file]
        else:
            ac3_options = ' '.join(ac3_options)
            cmd = f'ffmpeg -i "{input_file}" {ac3_options} "{output_file}"'

        logger.info('gen ac3 cmd = %s', cmd)
        try:
            subprocess.check_output(cmd, shell=shell, stdin=None, stderr=subprocess.STDOUT, timeout=7200)
        except BaseException as e:
            ret = False
            logger.warning('transcode gen ac3 failed %s params=[%s]\n %s', e, cmd, ' '.join(cmd))
            logger.warning(f'{traceback.print_exc()}')
    return ret


def ffmpeg_combine_video_audio(video_src, audio_src_list, output, shell, timeout=7200, **kwargs):
    '''
    调用ffmpeg将一个视频文件和多个音轨文件合并起来
    ffmpeg -i video_src -i audio_src1 -i audio_src2 -map 0:V:? -map 1:a -map 2:a -c copy -f mpegts -y output
    :param video_src: video source file
    :param audio_src_list: audio source file list
    :param output: target output file
    :param shell: whether is shell
    :param timeout: maximum timeout setting
    :param kwargs:
    :return:
    '''
    ret = True
    src_options = []
    combine_options = ['-map', '0:V:?']
    for i in range(len(audio_src_list)):
        src_options.append('-i')
        src_options.append(audio_src_list[i])
        combine_options.append('-map')
        combine_options.append(f'{i + 1}:a')
    if not shell:
        cmd = ['ffmpeg', '-i', video_src] + src_options + combine_options + ["-c", "copy", "-f", 'mpegts', '-y', output]
    else:
        src_options = ' '.join(src_options)
        combine_options = ' '.join(combine_options)
        cmd = 'ffmpeg -i "%s" %s %s -c copy -f mpegts -y %s' % (video_src, src_options, combine_options, output)
    try:
        subprocess.check_output(cmd, shell=True, stdin=None, stderr=subprocess.STDOUT, timeout=timeout)
    except BaseException as e:
        ret = False
        logger.warning('combine video audio failed %s params=[%s]\n %s', e, cmd, ' '.join(cmd))
        logger.warning(f'{traceback.print_exc()}')
    return ret


def process_video(input_file, output_file, media_info, offset, duration, target_lang, shell, copy_mode=True, gpu=True,
                  mp4=False, timeout=7200, decode_mode=True, **kwargs):
    '''
    1. 默认copy_mode, 如果input_file不是h264或h265, 则需要transcode. 如果有外挂.idx/.sub字幕也需要transcode
    2. 转码模式下:
        1. 有GPU但是码率不大, 则直接copy
        2. 有GPU但是码率过大, 则转成h265
        3. 没有GPU, 则转成h264
    :param input_file: input file
    :param output_file: target output file
    :param media_info: input file media info
    :param offset:
    :param duration:
    :param target_lang:
    :param shell: whether is shell
    :param copy_mode: prefer copy mode if video codec is h264 or h265, otherwise will transcod to h265
    :param gpu: whether to use gpu
    :param mp4:
    :param timeout: maximum timeout setting
    :param kwargs:
    :return:
    '''
    file_dur = float(media_info['format']['duration'])
    is_hevc = media_info['format']['have_hevc']
    have_264_hevc = media_info['format']['have_264_hevc']
    # have_4k = media_info['format']['have_4k']

    if file_dur != UNKNOW_SIZE and file_dur < offset + duration:
        raise Exception('invalid param file_dur=%f, offset=%f,duration=%f' % (file_dur, offset, duration))

    if not isinstance(target_lang,
                      dict) or 'iso639_1' not in target_lang.keys() or 'iso639_2' not in target_lang.keys():
        raise Exception(
            "invalid param target_lang=%s,must be dict  like {'iso639_1':'en','iso639_2':'eng'}" % (target_lang,))

    if file_dur == UNKNOW_SIZE:
        new_dur = UNKNOW_SIZE
    else:
        if duration == 0.0:
            new_dur = file_dur - offset
        else:
            new_dur = duration

    mp4_mode = ' -movflags +faststart -f mp4 '

    # gpu will transcode to hevc ,cpu will transcode to h264
    ts_mode = ' -vbsf hevc_mp4toannexb -f mpegts ' if gpu else ' -vbsf h264_mp4toannexb -f mpegts '

    # origin video have not h264 and h265 codec,change to transcode mode
    if not have_264_hevc:
        copy_mode = False

    hevc_copy_mode, target_bit_rate = get_transcode_bite_rate_params(input_file)
    if target_bit_rate == BIT_RATE_4K:
        timeout = 18000
    target_bit_rate = str(target_bit_rate)

    target_idx, target_idx_file, target_sub_file = get_sub_idx_subtitle_file(input_file, target_lang)
    if target_idx >= 0:
        # 有外部的.idx\.sub格式subtitle
        copy_mode = False
        hevc_copy_mode = False

    decoder_options = ' -vsync 0 ' if decode_mode else ''
    if gpu and have_264_hevc and not hevc_copy_mode and decode_mode:
        if is_hevc:
            decoder_options += ' -hwaccel cuvid -c:v hevc_cuvid '
        else:
            decoder_options += ' -hwaccel cuvid -c:v h264_cuvid '

    # copy mode if the video codec is h264
    if copy_mode and have_264_hevc:
        if is_hevc:
            ts_mode = ' -vbsf hevc_mp4toannexb -f mpegts '
        else:
            ts_mode = ' -vbsf h264_mp4toannexb -f mpegts '

    if not shell:
        # mp4_mode = ['-movflags', '+faststart', '-f', 'mp4']
        # ts_mode = ['-vbsf', 'hevc_mp4toannexb', '-f', 'mpegts']
        mp4_mode = mp4_mode.strip().split()
        ts_mode = ts_mode.strip().split()
        decoder_options = decoder_options.strip().split() if decode_mode else []

    if mp4:
        format_mode = mp4_mode
    else:
        format_mode = ts_mode

    if copy_mode:
        if not shell:
            cmd = ['ffmpeg', '-i', input_file, '-map', '0:V:?', '-vcodec', 'copy',
                   '-max_muxing_queue_size', '1500'] + format_mode + ['-y', output_file]
        else:
            cmd = ['ffmpeg -i "%s" -map 0:V:? -vcodec copy -max_muxing_queue_size 1500 %s -y %s' % (
                input_file, format_mode, output_file)]
    else:
        if gpu:
            if hevc_copy_mode:
                codec_str = ' -map 0:V:? -vcodec copy ' \
                            '-metadata title="" -metadata author="" -metadata copyright="" ' \
                            '-metadata comment="" -metadata description="" '
                if not shell:
                    codec_str = codec_str.strip().split(' ')
            else:
                if not shell:
                    codec_str = ['-map', '0:V:?', '-c:v', 'hevc_nvenc', '-max_muxing_queue_size',
                                 '1500', '-preset', 'fast', '-b:v', '{vid_bitrate}'.format(vid_bitrate=target_bit_rate),
                                 '-metadata', 'title=""', '-metadata', 'author=""', '-metadata', 'copyright=""',
                                 '-metadata', 'comment=""', '-metadata', 'description=""']
                else:
                    codec_str = ' -map 0:V:? -c:v hevc_nvenc -max_muxing_queue_size 1500 -preset fast ' \
                                '-b:v {vid_bitrate} -metadata title="" -metadata author="" ' \
                                '-metadata copyright="" -metadata comment="" -metadata description="" '.format(
                        vid_bitrate=target_bit_rate)
            if target_idx >= 0:
                # 有外部的.idx\.sub格式subtitle
                if new_dur == UNKNOW_SIZE or offset == 0.0:
                    # ffmpeg -i "American.mp4" -i "American.idx" -i "American.sub" -map 0:V:?  -map 0:a -c:v hevc_nvenc -max_muxing_queue_size 700 -preset fast -b:v 1500k -c:a aac -b:a 128k -metadata title="" -metadata author="" -metadata copyright="" -metadata comment="" -metadata description="" -filter_complex "[0:V][1:s:4]overlay=0:H-h" -vbsf hevc_mp4toannexb  -f mpegts  -y American.ts
                    if not shell:
                        cmd = ['ffmpeg', '-i', input_file, '-i', target_idx_file, '-i', target_sub_file] + codec_str \
                              + ['-filter_complex', '[0:V:?][1:s:%d]overlay=0:H-h' % target_idx] + format_mode + [
                                  '-y', output_file]
                    else:
                        cmd = [
                            'ffmpeg -i "%s" -i "%s" -i "%s" %s -filter_complex "[0:V:?][1:s:%d]overlay=0:H-h" %s -y %s'
                            % (input_file, target_idx_file, target_sub_file, codec_str, target_idx, format_mode,
                               output_file)]
                else:
                    # ffmpeg -i "American.mp4" -i "American.idx" -i "American.sub" -map 0:V:?  -map 0:a -c:v hevc_nvenc -max_muxing_queue_size 700 -preset fast -b:v 1500k -c:a aac -b:a 128k -metadata title="" -metadata author="" -metadata copyright="" -metadata comment="" -metadata description="" -filter_complex "[0:V][1:s:4]overlay=0:H-h" -vbsf hevc_mp4toannexb  -f mpegts  -y American.ts
                    if not shell:
                        cmd = ['ffmpeg', '-ss', str(offset), '-t', str(new_dur), '-i', input_file, '-i',
                               target_idx_file,
                               '-i', target_sub_file] + codec_str \
                              + ['-filter_complex', '[0:V:?][1:s:%d]overlay=0:H-h' % target_idx] \
                              + format_mode + ['-y', "%s" % output_file]
                    else:
                        cmd = [
                            'ffmpeg -ss %f  -t %f  -i "%s" -i "%s" -i "%s" %s -filter_complex "[0:V:?][1:s:%d]overlay=0:H-h" %s -y %s' % (
                                offset, new_dur, input_file, target_idx_file, target_sub_file, codec_str, target_idx,
                                format_mode, output_file)]
            else:
                if not shell:
                    cmd = ['ffmpeg'] + decoder_options + ['-i', "{input_file}".format(
                        input_file=input_file)] + codec_str + format_mode + ['-y', "%s" % output_file]
                else:
                    cmd = ['ffmpeg %s -i "%s" %s  %s -y %s' % (
                        decoder_options, input_file, codec_str, format_mode, output_file)]
        else:
            if not shell:
                cmd = ['ffmpeg', '-i', input_file, '-map', '0:V:?', '-c:v h264', '-preset', 'fast', '-b:v',
                       target_bit_rate,
                       '-max_muxing_queue_size', '1500', '-movflags', '+faststart', '-f', 'mp4', '-y',
                       "%s" % output_file]
            else:
                cmd = [
                    'ffmpeg -i "%s" -map 0:V:? -c:v h264 -preset fast -b:v %s '
                    '-max_muxing_queue_size 1500 -movflags +faststart -f mp4 -y "%s"' % (
                        input_file, target_bit_rate, output_file)]
    logger.info('cmd = %s', cmd)
    params = cmd
    ret = True
    try:
        subprocess.check_output(params, shell=shell, stdin=None, stderr=subprocess.STDOUT, timeout=timeout)
    except BaseException as e:
        ret = False
        logger.warning('transcode failed %s params=[%s]', e, params)
    if decode_mode and not ret:
        logger.info(f'try again, dont use decode mode')
        ret = process_video(input_file, output_file, media_info, offset, duration, target_lang, shell,
                            copy_mode=copy_mode,
                            gpu=gpu, mp4=mp4, timeout=7200, decode_mode=False)
    return ret, output_file


def check_file_duration(file, video_duration):
    result = True
    file_duration = int(float(ffprobe_get_media_duration(file)))
    # 时长差大于60s或者等于0s, 说明文件存在异常
    if abs(video_duration - file_duration) >= 60 or file_duration == 0:
        result = False
    logger.info(f'Original video duration={video_duration}')
    logger.info(f'Check {file} duration({file_duration}), result={result}')
    return result


def process_audio(input_file, output, media_info, shell, timeout=3600, add_dolby=True, **kwargs):
    '''
    1. 大于400k的转成320k, 反之copy
    2. 当音频声道数大于6需要改成2声道
    3. channel codec 处理:
        3.1. 有不是ac3和aac的音轨, 转成aac, 并添加ac3
            Stream #0:1 dts
            ffmpeg -i input_file -map 0:1 -vn -acodec aac -f mp4 -y output
            ffmpeg -i input_file -map 0:1 -vn -acodec ac3 -f mp4 -y output_ac3
        3.2. 已有ac3, 直接copy过去
            Stream #0:1 aac
            Stream #0:2 ac3
            ffmpeg -i input_file -map 0:1 -map 0:2 -vn -acodec copy -f mp4 -y output
        3.3. 只有ac3, 需要先转成aac, 并添加ac3
            Stream #0:1 ac3
            Stream #0:2 ac3
            ffmpeg -i input_file -map 0:1 -map 0:2 -vn -acodec aac -f mp4 -y output
            ffmpeg -i input_file -map 0:1 -map 0:2 -vn -acodec ac3 -f mp4 -y output_ac3
        3.4. 只有aac, 没有ac3, copy aac添加ac3 channel
            Stream #0:1 aac
            Stream #0:2 aac
            ffmpeg -i input_file -map 0:1 -map 0:2 -vn -acodec copy -f mp4 -y output
            ffmpeg -i input_file -map 0:1 -map 0:2 -vn -acodec ac3 -f mp4 -y output_ac3
    :param input_file: input file
    :param output: target output path
    :param media_info: input file media info
    :param shell: whether is shell
    :param timeout: maximum timeout setting
    :param add_dolby: whether to add dolby
    :param kwargs:
    :return:
    '''
    video_duration = kwargs.get('video_duration', 0)
    output_ac3_tmp = f'{output}.ac3.tmp'

    ac3_index_list = set(
        map(lambda stream: stream['index'] if stream['codec_name'].startswith('ac3') else -1, media_info['stream']))
    eac3_index_list = set(
        map(lambda stream: stream['index'] if stream['codec_name'].startswith('eac3') else -1, media_info['stream']))
    aac_index_list = set(
        map(lambda stream: stream['index'] if stream['codec_name'].find('aac') >= 0 else -1, media_info['stream']))
    audio_index_list = set(
        map(lambda stream: stream['index'] if stream['codec_type'].startswith('audio') else -1, media_info['stream']))
    ac3_index_list.discard(-1)
    eac3_index_list.discard(-1)
    aac_index_list.discard(-1)
    audio_index_list.discard(-1)
    all_ac3_list = list(ac3_index_list) + list(eac3_index_list)

    # 如果aac_index_list为空, 并且all_ac3_list的长度等于所有音轨的数量, 说明只有ac3/eac3音轨
    only_have_ac3 = False
    if not aac_index_list and len(all_ac3_list) == len(audio_index_list):
        only_have_ac3 = True

    '''
    1. acodec_mode控制是否转aac, 1代表需要转成aac, 0则不转
    2. 当只有ac3音轨或者有其他音轨的时候acodec_mode为 1, 需要转成aac.
    '''
    audio_state_list = []
    for stream in media_info['stream']:
        if stream['codec_type'].startswith('audio'):
            audio_state_dic = {'audio_index': stream['index'], 'codec_name': stream['codec_name']}
            if only_have_ac3:
                audio_state_dic['acodec_mode'] = 1
            else:
                # 如果有其他音轨或者有eac3音轨存在就需要转成aac
                if (stream['codec_name'].find('aac') < 0 and stream['codec_name'].find('ac3') < 0) or stream[
                    'codec_name'].startswith('eac3'):
                    audio_state_dic['acodec_mode'] = 1
                else:
                    audio_state_dic['acodec_mode'] = 0
            audio_state_dic['origin_bit_rate'] = stream['bit_rate']
            try:
                audio_state_dic['channels'] = int(stream['channels']) if stream[
                                                                             'channels'] and 'channels' in stream.keys() else 0
            except BaseException as e:
                audio_state_dic['channels'] = 0
            audio_state_dic['more_six_channel'] = 1 if int(stream['channels']) > SUPPORT_CHANNEL_NUMBER else 0
            audio_state_list.append(audio_state_dic)

    audio_src_list = []
    audio_process_result = False
    for audio_state in audio_state_list:
        audio_src_dic = {}
        bit_rate = AAC_BIT_RATE_MINIMUM
        audio_src_dic['target_codec_name'] = 'aac' if audio_state['acodec_mode'] == 1 else audio_state['codec_name']
        audio_tracks_list = [audio_state['audio_index']]
        audio_tmp = f'{output}_{audio_src_dic["target_codec_name"]}_{audio_state["audio_index"]}.tmp'
        # bit_mode = audio_state['bit_mode']
        channels = int(audio_state['channels'])
        origin_bit_rate = int(audio_state['origin_bit_rate'])
        # more_six_channel = audio_state['more_six_channel']
        '''
        aac: 声道为立体声, 原码率小于128修改为128, 大于128小于400修改为192, 大于400修改为320
        ac3: 两声道的码率为192, 大于等于六声道修改为六声道码率为320, 声道数不知道则为六声道码率为320
        '''
        if audio_src_dic["target_codec_name"].find('aac') >= 0:
            channels = 2
            if origin_bit_rate < AAC_BIT_RATE_MINIMUM:
                bit_rate = BITE_RATE_MIINIMUM
            elif origin_bit_rate < AAC_BIT_RATE_MAX:
                bit_rate = BITE_RATE_MEDIUM
            else:
                bit_rate = BITE_RATE_MAX
        if audio_src_dic["target_codec_name"].find('ac3') >= 0:
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

        audio_process_result = ffmpeg_audio_tracks_process(input_file, audio_tmp, audio_tracks_list, shell,
                                                           bit_rate=bit_rate, timeout=timeout, channels=channels,
                                                           target_codec=audio_src_dic["target_codec_name"])
        if audio_process_result:
            # 检查转码完成的文件时长是否异常
            check_audio_ret = check_file_duration(audio_tmp, video_duration)
            if not check_audio_ret:
                audio_process_result = False
                break
            audio_src_dic['src'] = audio_tmp
            audio_src_list.append(audio_src_dic)
        else:
            break
    if audio_process_result:
        # 排序: 将aac排在前面, ac3在后面
        for i in range(len(audio_src_list)):
            for j in range(0, len(audio_src_list) - i - 1):
                if audio_src_list[j]['target_codec_name'] != 'aac':
                    audio_src_list[j], audio_src_list[j + 1] = audio_src_list[j + 1], audio_src_list[j]

        # 当只有ac3或者没有ac3音轨的时候, 添加ac3 channel
        gen_ac3_ret = False
        if not all_ac3_list or only_have_ac3:
            gen_ac3_ret = gen_ac3_audio(input_file, output_ac3_tmp, all_ac3_list, audio_index_list, shell,
                                        add_dolby=add_dolby)
        if gen_ac3_ret:
            audio_src_list.append({'target_codec_name': 'ac3', 'src': output_ac3_tmp})

    return audio_src_list, audio_process_result


'''
subtitle_mode:0 没有subtitle
subtitle_mode:1 有外部的.idx\.sub格式subtitle
subtitle_mode:2 有外部的.srt格式subtitle
subtitle_mode:3 有内部.srt/.ass格式subtitle
优先级 1 > 2 >3
'''


def transcode(src, output, gpu=True, offset=0.0, duration=0.0, copy_mode=False, mp4=False,
              target_lang={'iso639_1': 'en', 'iso639_2': 'eng'}, timeout=7200, add_dolby=True, decode_mode=True):
    '''
    1. process_video 对视频进行copy or transcode处理
    2. process_audio 对音轨进行copy or transcode处理
    3. ffmpeg_combine_video_audio 将处理好的视频和音轨进行合并
    :param src: source file
    :param output: output file
    :param gpu: whether to use GPU
    :param offset:
    :param duration:
    :param copy_mode: prefer copy mode if video codec is h264 or h265, otherwise will transcod to h265
    :param mp4:
    :param target_lang:
    :param timeout: maximum timeout setting
    :param add_dolby: whether to add dolby
    :return:
    '''
    output_full_name = output
    output_tmp = output + '.tmp'
    video_tmp = output + '.video'
    media_info = ffprobe_get_media_info(src)
    if 'format' not in media_info or 'stream' not in media_info:
        raise Exception('invalid param file=%s' % (src))
    video_duration = int(float(media_info['format']['duration']))
    if video_duration <= 0:
        raise Exception(f'video duration({video_duration}) error')

    os_type = platform.system()
    shell = False if os_type.startswith('Windows') else True

    video_ret, video_src = process_video(src, video_tmp, media_info, offset, duration, target_lang, shell,
                                         copy_mode=copy_mode, gpu=gpu, mp4=mp4, decode_mode=decode_mode)

    audio_src_list = []
    audio_process_result = False
    if video_ret:
        audio_src_list, audio_process_result = process_audio(src, output, media_info, shell, timeout=timeout,
                                                             add_dolby=add_dolby, video_duration=video_duration)
    if audio_src_list and isinstance(audio_src_list[0], dict):
        audio_src_list = [i['src'] for i in audio_src_list]

    combine_ret = False
    if video_ret and audio_src_list and audio_process_result:
        combine_ret = ffmpeg_combine_video_audio(video_src, audio_src_list, output_tmp, shell)
    else:
        logger.warning(f'process video or audio error, video_ret={video_ret}, audio_ret={audio_process_result}')

    if combine_ret:
        shutil.move(output_tmp, output_full_name)
    try:
        os.remove(video_tmp)
    except BaseException as e:
        logger.warning(f'remove video tmp error {e}')
    for audio_tmp in audio_src_list:
        try:
            os.remove(audio_tmp)
        except BaseException as e:
            logger.warning(f'remove audio tmp error {e}')
    return combine_ret


def ffmpeg_download(url, output, ffmpeg_path, ts=True, timeout=3600,
                    useragent='Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.25 Safari/537.36 Core/1.70.3741.400 QQBrowser/10.5.3863.400'):
    '''
    :param url:  url to be downloaded
    :param output:  file full path to be saved
    :param ts: mpegts format or MP4 format for output
    :param timeout： timeout seconds to download
    :param useragent： useragent for the download
    :return:
    ret download result, TRUE success，False fail
    m3u8 duration seconds
    downloaded duration seconds
    '''
    ret = True
    start_time = time.time()

    expect_dur = ffprobe_get_media_duration(url)
    logger.info('Getting %s duration %f', url, expect_dur)
    # ffmpeg -i http://s5.14tvcdn.com/content/dy-etai-1.mp4/index.m3u8 -c copy -y dy-etai-1.mp4 > dy.txt 2>&1 &
    # ' -vbsf hevc_mp4toannexb -f mpegts '
    os_type = platform.system()
    if ts:
        mode = 'mpegts'
    else:
        mode = 'mp4'
    if ffmpeg_path:
        ffm_path = os.path.join(ffmpeg_path, "ffmpeg")
    else:
        ffm_path = 'ffmpeg'
    shell = True
    params = [
        '"{ffmpeg_path}" -user-agent "{useragent}" -i "{input}" -c copy -f {mode} -y "{output}"'.format(
            ffmpeg_path=ffm_path, useragent=useragent, input=url, mode=mode, output=output)]
    if os_type.startswith('Windows'):
        shell = False
        params = [
            ffm_path, "-user-agent", useragent, '-i', url, '-c', 'copy', '-f', mode, '-y', output]
    logger.info('Start download %s', params)
    try:
        subprocess.check_output(params, shell=shell, stdin=None, stderr=subprocess.STDOUT, timeout=timeout)
    except BaseException as e:
        ret = False
        logger.warning('download url %s to %s failed %s params=[%s]', url, output, e, params)
    end_time = time.time()
    downloaded_time = end_time - start_time
    actul_dur = ffprobe_get_media_duration(output)
    logger.info('cmd ret=%s,used %d seconds,expect_dur=%s, actul_dur=%s,params= %s',
                ret, int(downloaded_time), expect_dur, actul_dur, params)
    return ret, expect_dur, actul_dur


# transcode('E:\\ftp\\video\\VR.mp4', 'E:\\ftp\\video\\VR1.mp4')
# ffprobe -i http://s.14tvcdn.com/content/yy-gwdyj-hd-01.mp4/index.m3u8  -show_entries format=duration
# ffprobe -i "e:\media\国王的演讲(粤语)" -show_entries format=duration
def ffprobe_get_media_duration(file):
    logger.info('Getting {} duration'.format(file))
    params = ['ffprobe', '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=p=0', '-i']
    shell, params = __build_params(params, file)
    # params = ['ffprobe -show_entries format=duration -v quiet -of csv=p=0 -i "{file}"'.format(file=file)]
    try:
        dur = float(subprocess.check_output(params, shell=shell, stdin=None, stderr=subprocess.STDOUT).decode().strip())
    except BaseException as e:
        logger.warning(f"ffprobe_get_media_duration {e}")
        dur = UNKNOW_SIZE
    logger.info('dur= %s', dur)
    return dur


# ffprobe -i http://s.14tvcdn.com/content/yy-gwdyj-hd-01.mp4/index.m3u8  -show_entries format=bit_rate -v quiet   -v quiet -of csv=p=0
# ffprobe -i "e:\media\国王的演讲(粤语)" -show_entries format=bit_rate -v quiet   -v quiet -of csv=p=0
def get_transcode_bite_rate_params(file):
    '''
    :param file: file to be transcode
    :return:
        hevc_copy_mode, target_bit_rate kbps

    '''
    media_info = ffprobe_get_media_info(file)
    is_4k = False
    is_hevc = False
    bit_rate = 0
    if media_info and 'format' in media_info:
        is_4k = media_info['format']['have_4k']
        is_hevc = media_info['format']['have_hevc']
        bit_rate = int(media_info['format']['bit_rate'])

    hevc_copy_mode = False
    target_bit_rate = BIT_RATE_2K
    if is_hevc:
        if is_4k:
            if bit_rate > BIT_RATE_4K_MAX:
                target_bit_rate = BIT_RATE_4K
            else:
                hevc_copy_mode = True
        else:
            if bit_rate > BIT_RATE_2K_MAX:
                target_bit_rate = BIT_RATE_2K
            else:
                hevc_copy_mode = True
    else:
        if is_4k:
            target_bit_rate = BIT_RATE_4K
        else:
            target_bit_rate = BIT_RATE_2K

    if target_bit_rate > bit_rate and bit_rate > 0:
        target_bit_rate = bit_rate
    return hevc_copy_mode, target_bit_rate


'''
target_lang：Language family,ISO 639-2 ,three letters ,eg: eng por zho
    target_lang={'iso639_1':'en','iso639_2':'eng'}
'''


def ffprobe_get_subtitle_with_index(file, target_lang):
    # print('Getting {} media_subtitle'.format(file))
    params = ['ffprobe', '-print_format', 'json', '-show_streams', '-select_streams', 's', '-v', 'quiet',
              '-hide_banner', '-i']
    # params = ['ffprobe -print_format json -show_streams -select_streams s -v quiet -hide_banner -i "{file}"'.format(
    #     file=file)]
    shell, params = __build_params(params, file)
    have_subtitle = False
    if isinstance(target_lang, dict):
        target_lang = target_lang['iso639_2']
    subtitle_index = -1
    subtitle_file = file
    subtitle_lang = ''
    try:
        info = str(
            subprocess.check_output(params, shell=shell, stdin=None, stderr=subprocess.STDOUT).decode().strip()).lower()
        # print(info)
        sub_info = json.loads(info)
        sub_streams = sub_info['streams']
        logger.info('sub_streams %s', sub_streams)
        if not not sub_streams:
            have_subtitle = True
            # try to get the subtitle_index with target_lang
            index = 0
            for stream in sub_streams:
                if 'tags' in stream.keys() and 'language' in stream['tags'] and stream['tags'][
                    'language'] == target_lang:
                    subtitle_index = index
                    break
                index += 1

            # try to get eng subtitle index of the input file
            if subtitle_index < 0:
                index = 0
                for stream in sub_streams:
                    if 'tags' in stream.keys() and 'language' in stream['tags'] and stream['tags']['language'] == 'eng':
                        subtitle_index = index
                        subtitle_lang = 'eng'
                        break
                    index += 1

            # try to get default subtitle index of the input file
            if subtitle_index < 0:
                index = 0
                for stream in sub_streams:
                    if 'disposition' in stream.keys() and stream['disposition']['default'] == 1:
                        subtitle_index = index
                        break
                    index += 1

            # get the  first subtitle index of the input file
            if subtitle_index < 0:
                subtitle_index = 0

            if not subtitle_lang:
                stream = sub_streams[subtitle_index]
                if 'tags' in stream.keys() and 'language' in stream['tags']:
                    subtitle_lang = stream['tags']['language']
                else:
                    subtitle_lang = 'default'

    except BaseException as e:
        have_subtitle = False
        subtitle_index = -1
        subtitle_file = ''
        subtitle_lang = ''
    logger.info(
        "have_subtitle {} {} subtitle_index={} lang={}".format(file, have_subtitle, subtitle_index, subtitle_lang))
    return have_subtitle, subtitle_file, subtitle_index, subtitle_lang


def subtitles_to_srt(file, shell=True):
    logger.info(F"will start to convert file: {file} to srt")
    name_without_ext, _ = os.path.splitext(file)
    ext = '.srt'
    new_name = name_without_ext + ext
    if os.path.exists(new_name):
        ext = f"{_}.srt"
        new_name = name_without_ext + ext
    if not not shell:
        params = ['ffmpeg -i "%s" "%s"' % (file, new_name)]
    else:
        params = ['ffmpeg', "-i", file, new_name]  # windows
    ret = False
    logger.info(F"convert to srt params: {params}")
    try:
        subprocess.check_output(
            params, shell=shell, stdin=None, stderr=subprocess.STDOUT, timeout=60).decode().strip().lower()
        ret = True
    except BaseException as e:
        logger.warning(F'subtitle: {file} convert to srt, error: {e}')

    if not not ret:
        try:
            os.remove(file)
        except FileNotFoundError:
            pass

    return ret, ext


def ffprobe_get_media_info(file_path, timeout=60):
    '''
    get media info of the file_path
    :param file_path: path of the media to be detect
    :return:
        {
        "stream": [
            {
                "index": 0,
                "codec_name": "h264",
                "codec_long_name": "MPEG-4 part 2",
                "codec_type": "video",
                "codec_tag_string": "XVID",
                "codec_tag": "0x44495658",
                "language": "eng",
                "width": "1280",
                "height": "720",
            },
            {
                "index": 1,
                "codec_name": "mp3",
                "codec_long_name": "MP3 (MPEG audio layer 3)",
                "codec_type": "audio",
                "codec_tag_string": "U[0][0][0]",
                "codec_tag": "0x0055",
                 "language": "",
            }
        ],
        "format": {
            "filename":"http://192.99.195.52:2086/movie/A.Oracao.Nao.Falha.2018.mp4"
            "nb_vstreams": 1,
            "nb_astreams": 1,
            "nb_sstreams":0,
            "have_264_hevc": 1,
            "have_hevc": 1,
            "have_4k": 1,
            "format_name": "mpegts",
            "format_long_name": "MPEG-TS (MPEG-2 Transport Stream)",
            "duration": "63.466444",
            "bit_rate": "3137794",
            "size": "941246464"
        }
    }
    '''

    '''
    ffprobe -v quiet -print_format json -show_format -show_streams -hide_banner -i E:\media\globe\20190217_113739.ts
    {
        "streams": [
            {
                "index": 0,
                "codec_name": "h264",
                "codec_long_name": "MPEG-4 part 2",
                "codec_type": "video",                
                "codec_tag_string": "XVID",
                "codec_tag": "0x44495658",
                "tags": {
                    "language": "eng",
                }
            },
            {
                "index": 1,
                "codec_name": "mp3",
                "codec_long_name": "MP3 (MPEG audio layer 3)",
                "codec_type": "audio",
                "codec_tag_string": "U[0][0][0]",
                "codec_tag": "0x0055",
                 "tags": {
                    "language": "eng",
                }
            }
        ],
        "format": {          
            "nb_streams": 2,
            "nb_programs": 0,            
            "format_name": "mpegts",
            "format_long_name": "MPEG-TS (MPEG-2 Transport Stream)",     
            "duration": "63.466444",             
            "bit_rate": "3137794"       
        }
    }
    '''

    def is_avc_or_hevc_codec(codec_name):
        return codec_name.startswith('h264') or codec_name.startswith('hevc')

    def is_hevc_codec(codec_name):
        return codec_name.startswith('hevc')

    def is_4k_video(width: 'int'):
        return int(width) >= 3000

    params = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', '-hide_banner', '-i']
    shell, params = __build_params(params, file_path)
    # params = [
    #     'ffprobe -v quiet -print_format json -show_format -show_streams -hide_banner -analyzeduration 60000 -i "{file}"'.format(
    #         file=file_path)]
    res = {}
    try:
        media_info_str = str(
            subprocess.check_output(params, shell=shell, stdin=None, stderr=subprocess.STDOUT,
                                    timeout=timeout).decode().strip()).lower()
        # print(info)
        media_info = json.loads(media_info_str)
        sub_streams = media_info['streams']
        # print(sub_streams)
        have_264_hevc = False
        have_hevc = False
        have_4k = False
        if not not sub_streams:
            res = {
                'stream': [],
                'format': {}
            }

            video_num = 0
            audio_num = 0
            subtitle_num = 0
            for sub_stream in sub_streams:
                if 'codec_time_base' in sub_stream and not sub_stream['codec_time_base'].startswith("0/1"):
                    stream = {}
                    stream['index'] = sub_stream['index']
                    stream['codec_name'] = sub_stream['codec_name']
                    stream['codec_long_name'] = sub_stream['codec_long_name']
                    stream['codec_type'] = sub_stream['codec_type']
                    stream['codec_tag_string'] = sub_stream['codec_tag_string']
                    stream['codec_tag'] = sub_stream['codec_tag']
                    stream['language'] = ''
                    if 'tags' in sub_stream.keys() and 'language' in sub_stream['tags']:
                        stream['language'] = sub_stream['tags']['language']

                    if sub_stream['codec_type'] == "video":
                        stream['width'] = sub_stream['width']
                        stream['height'] = sub_stream['height']
                        video_num += 1
                        have_264_hevc = have_264_hevc or is_avc_or_hevc_codec(sub_stream['codec_name'])
                        have_hevc = have_hevc or is_hevc_codec(sub_stream['codec_name'])
                        have_4k = have_4k or is_4k_video(sub_stream['width'])
                    elif sub_stream['codec_type'] == "audio":
                        stream['sample_rate'] = sub_stream['sample_rate'] if 'sample_rate' in sub_stream else ''
                        stream['bit_rate'] = sub_stream['bit_rate'] if 'bit_rate' in sub_stream else '0'
                        stream['channels'] = sub_stream['channels'] if 'channels' in sub_stream else 2
                        stream['channel_layout'] = sub_stream[
                            'channel_layout'] if 'channel_layout' in sub_stream else ''
                        audio_num += 1
                    elif sub_stream['codec_type'] == "subtitle":
                        subtitle_num += 1

                    # cover in mkv - "codec_time_base": "0/1"
                    res['stream'].append(stream)

            m_format = media_info['format']
            media_format = {}
            media_format['filename'] = m_format['filename'] if 'filename' in m_format else ''
            media_format['format_name'] = m_format['format_name'] if 'format_name' in m_format else ''
            media_format['format_long_name'] = m_format['format_long_name'] if 'format_long_name' in m_format else 'und'
            media_format['duration'] = m_format['duration'] if 'duration' in m_format else '0'
            media_format['bit_rate'] = m_format['bit_rate'] if 'bit_rate' in m_format else '0'
            media_format['size'] = m_format['size'] if 'size' in m_format else '0'
            media_format['have_264_hevc'] = 1 if have_264_hevc else 0
            media_format['have_hevc'] = 1 if have_hevc else 0
            media_format['have_4k'] = 1 if have_4k else 0
            media_format['nb_vstreams'] = video_num
            media_format['nb_astreams'] = audio_num
            media_format['nb_sstreams'] = subtitle_num
            res['format'] = media_format
    except BaseException as e:
        logger.debug("traceback %s", traceback.format_exc())
        logger.info('ffprobe_get_media_info %s', e)
        res = {}

    return res


def ffmpeg_extract_subtitles_with_index(input, output_file, index):
    # ffmpeg -i MultipleSubtitle1.mkv -map 0:0  -f srt -y MultipleSubtitle1.srt
    # ffmpeg -v quiet -i MultipleSubtitle1.mkv -map 0:0 -f srt -y MultipleSubtitle1.srt
    tmp_file = output_file + '.tmp'
    result = False
    os_type = platform.system()
    if os.path.exists(output_file):
        result = True
        return result
    if os_type.startswith('Windows'):
        shell = False
        params = ["ffmpeg", "-i", "{input}".format(input=input), "-map", "0:{index}".format(index=index),
                  "-f", "srt", "-y", "{output}".format(output=tmp_file)]
    else:
        shell = True
        params = ['ffmpeg -i "{input}" -map 0:{index} -f srt -y "{output}"'.format(input=input, index=index,
                                                                                   output=tmp_file)]
    print(params)
    try:
        subprocess.check_output(params, shell=shell, stdin=None, stderr=subprocess.STDOUT).decode().strip()
        if os.path.exists(tmp_file) and os.path.getsize(tmp_file) > 0x400:
            shutil.move(tmp_file, output_file)
            result = True
        else:
            try:
                os.remove(tmp_file)
            except:
                pass
    except BaseException as exception:

        logger.info('exception %s', exception)

    logger.info('ffmpeg_extract_subtitles_with_index (input,output,result)=%s,%s,%s', input, output_file, result)
    return result


def ffprobe_channel_alive(url, timeout=30):
    '''
    直播频道在线check
    :param url:
    :return:
    '''
    alive = False
    video_info = {}
    if not not url:
        ff_media_info = ffprobe_get_media_info(url, timeout)
        # 直播频道文件大小为0，点播文件必须>0
        if "format" in ff_media_info and "format_name" in ff_media_info['format'] \
                and ((ff_media_info['format']['format_name'] == "mpegts" and ff_media_info['format']['size'] == '0')
                     or (ff_media_info['format']['format_name'] == "hls" and ff_media_info['format']['size'] != '0')
        ) \
                and ff_media_info['stream']:
            streams = ff_media_info['stream']
            for stream in streams:
                if stream["codec_type"] == "video":
                    video_info['width'] = stream['width']
                    video_info['height'] = stream['height']
                    video_info['codec_name'] = stream['codec_name']
            alive = True
    logger.debug("%s alive %s", url, alive)
    return alive, video_info


def ffmpeg_extrat_subtitles(input, out_path):
    # print('Getting {} media_subtitle'.format(file))
    # C:/ffmpeg-4.2.2-win64-static/bin/
    pub_params = ['ffprobe', '-show_streams', '-print_format', 'json', '-select_streams', 's', '-v', 'quiet',
                  '-hide_banner', '-i']
    shell, params = __build_params(pub_params, input)
    have_subtitle = False

    # input_file_path = os.path.dirname(input)
    input_file_name = os.path.basename(input)
    input_file_name_without_ext = os.path.splitext(input_file_name)[0]
    subtitle_list = []

    try:
        info = str(
            subprocess.check_output(params, shell=shell, stdin=None, stderr=subprocess.STDOUT).decode().strip()).lower()
        # print(info)
        sub_info = json.loads(info)
        sub_streams = sub_info['streams']
        logger.info('sub_streams=%s', sub_streams)
        if not not sub_streams:
            have_subtitle = True
            # try to get the subtitle_index with target_lang
            index = 0
            for stream in sub_streams:
                # print('stream=', stream)
                subtitle_index = str(stream['index'])
                subtitle_lang = 'und' + str(index)
                index += 1
                if 'tags' in stream.keys() and 'language' in stream['tags']:
                    subtitle_lang = stream['tags']['language']

                subtitle_ext = '.srt_' + subtitle_lang
                output_file = os.path.join(out_path, input_file_name_without_ext + subtitle_ext)
                # print('will call ffmpeg_extract_subtitles_with_index=', input,output_file,subtitle_index)
                if os.path.exists(output_file):
                    continue
                res = ffmpeg_extract_subtitles_with_index(input, output_file, subtitle_index)
                if res:
                    subtitle_info = {}
                    subtitle_info['language'] = subtitle_lang
                    subtitle_info['stream_name'] = input_file_name
                    subtitle_info['stream_index'] = subtitle_index
                    subtitle_info['path'] = output_file
                    subtitle_list.append(subtitle_info)


    except BaseException as e:
        logger.debug("traceback %s", traceback.format_exc())
        have_subtitle = False

    logger.info("have_subtitle {} {} subtitle_list={}".format(have_subtitle, input, subtitle_list))
    return have_subtitle, subtitle_list


# ffprobe -print_format csv -show_streams -select_streams v -hide_banner -v quiet -i /home/cdn/diskb/306_35707
def ffprobe_is_hevc(file):
    # print('Getting {} media_subtitle'.format(file))
    params = ['ffprobe -print_format csv -show_streams -select_streams v -hide_banner -v quiet -i "{input}"'.format(
        input=file)]
    is_hevc = False
    try:
        info = str(
            subprocess.check_output(params, shell=True, stdin=None, stderr=subprocess.STDOUT).decode().strip()).lower()
        logger.info("info =%s", info)
        index = info.find('hevc')
        if index >= 0:
            is_hevc = True
    except BaseException as e:
        is_hevc = False
    logger.info("is_hevc {} {}".format(file, is_hevc))
    return is_hevc


# ffprobe -print_format csv -show_streams -select_streams a -hide_banner -v quiet -i /home/disk1/cdn/394_75760
def ffprobe_is_ac3(file):
    # print('Getting {} media_subtitle'.format(file))
    params = ['ffprobe', '-print_format', 'csv', '-show_streams', '-select_streams', 'a', '-hide_banner', '-v', 'quiet',
              '-i']
    shell, params = __build_params(params, file)
    # params = ['ffprobe -print_format csv -show_streams -select_streams a -hide_banner -v quiet -i "{input}"'.format(
    #     input=file)]
    is_ac3 = False
    try:
        info = str(
            subprocess.check_output(params, shell=shell, stdin=None, stderr=subprocess.STDOUT).decode().strip()).lower()
        logger.info("info =%s", info)
        index = info.find('ac3')
        if index >= 0:
            is_ac3 = True
    except BaseException as e:
        is_ac3 = False
    logger.info("is_ac3 {} {}".format(file, is_ac3))
    return is_ac3


def file_mime_encoding(file, backup=True, **kwargs):
    # print('Getting {} media_subtitle'.format(file))
    '''
    params = ['file']
    params.extend(['--mime-encoding'])
    params.extend([file])
    '''
    backup_path = kwargs.get('backup_path', None)
    # params = ['file --mime-encoding "{file}"'.format(file=file)]
    try:
        # info = str(subprocess.check_output(params, shell=True, stdin=None, stderr=subprocess.STDOUT).decode().strip())
        # logger.info('file_mime_encoding file =%s', info)
        s = open(file, 'rb').read()
        mime_encoding = chardet.detect(s)['encoding']
        # if not not mime_encoding and not mime_encoding.lower().startswith('utf-8'):
        logger.info('*********************************************************************')
        logger.info('mime encodinng: %s' % mime_encoding)
        logger.info('*********************************************************************')
        if not not mime_encoding:
            if backup_path:
                name_es = os.path.basename(file)
                backup_output = os.path.join(backup_path, name_es)
                org_name = backup_output + '.org'
            else:
                org_name = file + '.org'
            tmp_name = file + '.tmp'

            if mime_encoding.lower().startswith('unknown-8bit'):
                mime_encoding = 'iso-8859-1'
            if mime_encoding.lower() == 'gb2312':
                mime_encoding = 'GBK'
            # iconv -f ' utf-8' -t 'utf-8' '/mnt/udisk/bludv_movie/Mãe! 2017 (720p) WWW.BLUDV.COM/Mae.2017.720p.BluRay.6CH.x264.DUAL-WWW.BLUDV.COM.srt' -o 11
            params = ['iconv -f {mime_encoding} -t utf-8 "{input}" -o "{output}"'.format(mime_encoding=mime_encoding,
                                                                                         input=file, output=tmp_name)]
            logger.info('will convert to utf-8 from %s,filename %s,backup %s', mime_encoding, file, backup)
            info = str(subprocess.check_output(params, shell=True, stdin=None,
                                               stderr=subprocess.STDOUT).decode().strip()).lower()
            logger.info('file_mime_encoding iconv= %s', info)
            if not info and os.path.getsize(tmp_name) > 0:
                if backup and not os.path.exists(org_name):
                    shutil.move(file, org_name)
                else:
                    os.remove(file)
                    logger.info('file_mime_encoding remove old =%s', file)
                logger.info('rename from %s to %s, backup=%s', tmp_name, file, backup)
                shutil.move(tmp_name, file)
                mime_encoding = 'utf-8'
            else:
                mime_encoding = ''
                # iconv -f iso-8859-1  -t UTF-8 /mnt/2.5/bludv/encoding/12.Heróis.2018.720p.BluRay.6CH.x264.DUAL-WWW.BLUDV.COM.srt-org -o /mnt/2.5/bludv/encoding/12.Heróis.2018.720p.BluRay.6CH.x264.DUAL-WWW.BLUDV.COM.srt
    except BaseException as e:
        logger.warning('unknown error, please check')
        mime_encoding = ''

    return mime_encoding


def test():
    # vid='/home/felix/tmp/1.rmvb'
    # len=ffprobe_get_media_duration(vid)
    # newlen=len-10
    # print(newlen)
    transcode('E:/test/test_stream/MP4_HPL40_30fps_channel_id_51_dolby.mp4',
              'E:/test/test_stream/MP4_HPL40_30fps_channel_id_51_aac_dolby.ts', False, copy_mode=True)
    transcode('E:/test/test_stream/MP4_HPL40_30fps_channel_id_51_aac.mp4',
              'E:/test/test_stream/MP4_HPL40_30fps_channel_id_51_aac.ts', False, copy_mode=True)
    # ffprobe -show_entries format=duration -v quiet -of csv=p=0  -i 'xxx.mp4'
    # ffprobe -i '/mnt/2.6/www/video/www.dy2018.net/output/2018_03_22/[阳光电影www.ygdy8.com].女皇.BD.720p.中英双字幕.mp4' -show_entries format=duration -v quiet -of csv=p=0
    # len=ffprobe_get_media_duration('/mnt/2.6/www/video1/www.dy2018.net/output/sp1/[电影天堂www.dy2018.net].BBC：植物之歌(第一集).BD.720p.中英双字幕.mkv')
    # print(float(len)-10)
    # ffprobe_contain_media_subtitle("E:\\ftp\\video\\Alex.Inc.S01E01.720p.HDTV.x264-FLEET.mkv")
    # lang: por葡语 eng 英语
    have_sub, subtitle_file, index, sub_lang = ffprobe_get_subtitle_with_index(
        "E:\\media\\test_transecoder\\MultipleSubtitle3.mkv", 'por')
    print('have_sub={0}, subtitle_index={1}'.format(have_sub, index))
    have_sub, subtitle_file, index, sub_lang = ffprobe_get_subtitle_with_index(
        "E:\\media\\test_transecoder\\MultipleSubtitle3.mkv", 'spa')
    print('have_sub={0}, subtitle_index={1}'.format(have_sub, index))
    have_sub, subtitle_file, index, sub_lang = ffprobe_get_subtitle_with_index(
        "E:\\media\\test_transecoder\\MultipleSubtitle3.mkv", 'eng')
    print('have_sub={0}, subtitle_index={1}'.format(have_sub, index))
    # ffprobe_get_subtitle_with_index("E:\\media\\test_transecoder\\American.mp4",'por')
    get_srt_subtitle_file("E:\\media\\test_transecoder\\MultipleSubtitle3.mkv")
    get_sub_idx_subtitle_file("E:\\media\\test_transecoder\\American.mp4", 'pt')
    transcode("E:\\media\\test_transecoder\\American.mp4", "E:\\media\\test_transecoder\\American.ts", gpu=True,
              target_lang={'iso639_1': 'en', 'iso639_2': 'eng'})
    transcode("E:\\media\\test_transecoder\\American.mp4", "E:\\media\\test_transecoder\\American.ts", gpu=True,
              target_lang={'iso639_1': 'pt', 'iso639_2': 'por'})
    # transcode("E:\\media\\test_transecoder\\American.mp4","E:\\media\\test_transecoder\\American.mp4",gpu=True,target_lang='pt')
    mime_encoding = file_mime_encoding(
        'E:\\media\\test_transecoder\\12.Heróis.2018.720p.BluRay.6CH.x264.DUAL-WWW.BLUDV.COM.srt')
    ffmpeg_extrat_subtitles('\\\\192.168.2.5\\felix\\video\\test_transecoder\\MultipleSubtitle1.mkv',
                            '\\\\192.168.2.5\\felix\\video\\test_transecoder\\')

    mime_encoding = file_mime_encoding(
        'E:\media_toolset\test\Transformers Dark of the Moon 2011 TS XViD - IMAGiNE.chs.srt')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d_%H:%M:%S')
    file_name = "/home/www/video/www.juraganfilm.org/downloaded/We Are All Alone (2020)s1e26.mp4.tmp"
    dur = ffprobe_get_media_duration(file_name)
    print(file_name, " dur=", dur)

    test()
    # file_mime_encoding('/mnt/udisk/bludv_movie/Mãe! 2017 (720p) WWW.BLUDV.COM/Mae.2017.720p.BluRay.6CH.x264.DUAL-WWW.BLUDV.COM.srt.org')
    # ffmpeg_extrat_subtitles('\\\\192.168.2.5\\felix\\video\\test_transecoder\\MultipleSubtitle1.mkv','\\\\192.168.2.5\\felix\\video\\test_transecoder\\')
    # mime_encoding = file_mime_encoding('E:\\media\\test_transecoder\\12.Heróis.2018.720p.BluRay.6CH.x264.DUAL-WWW.BLUDV.COM.srt')

    '''
    transcode("D:\\www\\www.kkwu.com\\downloaded\\登月第一人.mp4", "D:\\www\\www.kkwu.com\\transcoded\\登月第一人.ts", gpu=True,
              copy_mode=True, mp4=False, target_lang={'iso639_1': 'pt', 'iso639_2': 'por'})
    '''
'''
Language family,ISO language name,Native name,639-1,639-2/T,639-2/B,639-3
Northwest Caucasian Abkhazian   аҧсуа бызшәа, аҧсшәа    ab  abk abk abk
Afro-Asiatic    Afar    Afaraf  aa  aar aar aar
Indo-European   Afrikaans   Afrikaans   af  afr afr afr
Niger–Congo Akan    Akan    ak  aka aka aka + 2
Indo-European   Albanian    Shqip   sq  sqi alb sqi + 4
Afro-Asiatic    Amharic አማርኛ    am  amh amh amh
Afro-Asiatic    Arabic  العربية ar  ara ara ara + 30
Indo-European   Aragonese   aragonés    an  arg arg arg
Indo-European   Armenian    Հայերեն hy  hye arm hye
Indo-European   Assamese    অসমীয়া as  asm asm asm
Northeast Caucasian Avaric  авар мацӀ, магӀарул мацӀ    av  ava ava ava
Indo-European   Avestan avesta  ae  ave ave ave
Aymaran Aymara  aymar aru   ay  aym aym aym + 2
Turkic  Azerbaijani azərbaycan dili az  aze aze aze + 2
Niger–Congo Bambara bamanankan  bm  bam bam bam
Turkic  Bashkir башҡорт теле    ba  bak bak bak
Language isolate    Basque  euskara, euskera    eu  eus baq eus
Indo-European   Belarusian  беларуская мова be  bel bel bel
Indo-European   Bengali বাংলা   bn  ben ben ben
Indo-European   Bihari languages    भोजपुरी bh  bih bih 
Creole  Bislama Bislama bi  bis bis bis
Indo-European   Bosnian bosanski jezik  bs  bos bos bos
Indo-European   Breton  brezhoneg   br  bre bre bre
Indo-European   Bulgarian   български език  bg  bul bul bul
Sino-Tibetan    Burmese ဗမာစာ   my  mya bur mya
Indo-European   Catalan, Valencian  català, valencià    ca  cat cat cat
Austronesian    Chamorro    Chamoru ch  cha cha cha
Northeast Caucasian Chechen нохчийн мотт    ce  che che che
Niger–Congo Chichewa, Chewa, Nyanja chiCheŵa, chinyanja ny  nya nya nya
Sino-Tibetan    Chinese 中文 (Zhōngwén), 汉语, 漢語   zh  zho chi zho + 13
Turkic  Chuvash чӑваш чӗлхи cv  chv chv chv
Indo-European   Cornish Kernewek    kw  cor cor cor
Indo-European   Corsican    corsu, lingua corsa co  cos cos cos
Algonquian  Cree    ᓀᐦᐃᔭᐍᐏᐣ cr  cre cre cre + 6
Indo-European   Croatian    hrvatski jezik  hr  hrv hrv hrv
Indo-European   Czech   čeština, český jazyk    cs  ces cze ces
Indo-European   Danish  dansk   da  dan dan dan
Indo-European   Divehi, Dhivehi, Maldivian  ދިވެހި  dv  div div div
Indo-European   Dutch, Flemish  Nederlands, Vlaams  nl  nld dut nld
Sino-Tibetan    Dzongkha    རྫོང་ཁ  dz  dzo dzo dzo
Indo-European   English English en  eng eng eng
Constructed Esperanto   Esperanto   eo  epo epo epo
Uralic  Estonian    eesti, eesti keel   et  est est est + 2
Niger–Congo Ewe Eʋegbe  ee  ewe ewe ewe
Indo-European   Faroese føroyskt    fo  fao fao fao
Austronesian    Fijian  vosa Vakaviti   fj  fij fij fij
Uralic  Finnish suomi, suomen kieli fi  fin fin fin
Indo-European   French  français, langue française  fr  fra fre fra
Niger–Congo Fulah   Fulfulde, Pulaar, Pular ff  ful ful ful + 9
Indo-European   Galician    Galego  gl  glg glg glg
South Caucasian Georgian    ქართული ka  kat geo kat
Indo-European   German  Deutsch de  deu ger deu
Indo-European   Greek (modern)  ελληνικά    el  ell gre ell
Tupian  Guaraní Avañe'ẽ gn  grn grn grn + 5
Indo-European   Gujarati    ગુજરાતી gu  guj guj guj
Creole  Haitian, Haitian Creole Kreyòl ayisyen  ht  hat hat hat
Afro-Asiatic    Hausa   (Hausa) هَوُسَ  ha  hau hau hau
Afro-Asiatic    Hebrew (modern) עברית   he  heb heb heb
Niger–Congo Herero  Otjiherero  hz  her her her
Indo-European   Hindi   हिन्दी, हिंदी   hi  hin hin hin
Austronesian    Hiri Motu   Hiri Motu   ho  hmo hmo hmo
Uralic  Hungarian   magyar  hu  hun hun hun
Constructed Interlingua Interlingua ia  ina ina ina
Austronesian    Indonesian  Bahasa Indonesia    id  ind ind ind
Constructed Interlingue Originally called Occidental; then Interlingue after WWII   ie  ile ile ile
Indo-European   Irish   Gaeilge ga  gle gle gle
Niger–Congo Igbo    Asụsụ Igbo  ig  ibo ibo ibo
Eskimo–Aleut    Inupiaq Iñupiaq, Iñupiatun  ik  ipk ipk ipk + 2
Constructed Ido Ido io  ido ido ido
Indo-European   Icelandic   Íslenska    is  isl ice isl
Indo-European   Italian Italiano    it  ita ita ita
Eskimo–Aleut    Inuktitut   ᐃᓄᒃᑎᑐᑦ  iu  iku iku iku + 2
Japonic Japanese    日本語 (にほんご)  ja  jpn jpn jpn
Austronesian    Javanese    ꦧꦱꦗꦮ, Basa Jawa jv  jav jav jav
Eskimo–Aleut    Kalaallisut, Greenlandic    kalaallisut, kalaallit oqaasii  kl  kal kal kal
Dravidian   Kannada ಕನ್ನಡ   kn  kan kan kan
Nilo-Saharan    Kanuri  Kanuri  kr  kau kau kau + 3
Indo-European   Kashmiri    कश्मीरी, كشميري‎    ks  kas kas kas
Turkic  Kazakh  қазақ тілі  kk  kaz kaz kaz
Austroasiatic   Central Khmer   ខ្មែរ, ខេមរភាសា, ភាសាខ្មែរ  km  khm khm khm
Niger–Congo Kikuyu, Gikuyu  Gĩkũyũ  ki  kik kik kik
Niger–Congo Kinyarwanda Ikinyarwanda    rw  kin kin kin
Turkic  Kirghiz, Kyrgyz Кыргызча, Кыргыз тили   ky  kir kir kir
Uralic  Komi    коми кыв    kv  kom kom kom + 2
Niger–Congo Kongo   Kikongo kg  kon kon kon + 3
Koreanic    Korean  한국어 ko  kor kor kor
Indo-European   Kurdish Kurdî, کوردی‎   ku  kur kur kur + 3
Niger–Congo Kuanyama, Kwanyama  Kuanyama    kj  kua kua kua
Indo-European   Latin   latine, lingua latina   la  lat lat lat
Indo-European   Luxembourgish, Letzeburgesch    Lëtzebuergesch  lb  ltz ltz ltz
Niger–Congo Ganda   Luganda lg  lug lug lug
Indo-European   Limburgan, Limburger, Limburgish    Limburgs    li  lim lim lim
Niger–Congo Lingala Lingála ln  lin lin lin
Tai–Kadai   Lao ພາສາລາວ lo  lao lao lao
Indo-European   Lithuanian  lietuvių kalba  lt  lit lit lit
Niger–Congo Luba-Katanga    Kiluba  lu  lub lub lub
Indo-European   Latvian latviešu valoda lv  lav lav lav + 2
Indo-European   Manx    Gaelg, Gailck   gv  glv glv glv
Indo-European   Macedonian  македонски јазик    mk  mkd mac mkd
Austronesian    Malagasy    fiteny malagasy mg  mlg mlg mlg + 10
Austronesian    Malay   Bahasa Melayu, بهاس ملايو‎  ms  msa may msa + 13
Dravidian   Malayalam   മലയാളം  ml  mal mal mal
Afro-Asiatic    Maltese Malti   mt  mlt mlt mlt
Austronesian    Maori   te reo Māori    mi  mri mao mri
Indo-European   Marathi मराठी   mr  mar mar mar
Austronesian    Marshallese Kajin M̧ajeļ    mh  mah mah mah
Mongolic    Mongolian   Монгол хэл  mn  mon mon mon + 2
Austronesian    Nauru   Dorerin Naoero  na  nau nau nau
Dené–Yeniseian  Navajo, Navaho  Diné bizaad nv  nav nav nav
Niger–Congo North Ndebele   isiNdebele  nd  nde nde nde
Indo-European   Nepali  नेपाली  ne  nep nep nep
Niger–Congo Ndonga  Owambo  ng  ndo ndo ndo
Indo-European   Norwegian Bokmål    Norsk Bokmål    nb  nob nob nob
Indo-European   Norwegian Nynorsk   Norsk Nynorsk   nn  nno nno nno
Indo-European   Norwegian   Norsk   no  nor nor nor + 2
Sino-Tibetan    Sichuan Yi, Nuosu   ꆈꌠ꒿ Nuosuhxop   ii  iii iii iii
Niger–Congo South Ndebele   isiNdebele  nr  nbl nbl nbl
Indo-European   Occitan occitan, lenga d'òc oc  oci oci oci
Algonquian  Ojibwa  ᐊᓂᔑᓈᐯᒧᐎᓐ    oj  oji oji oji + 7
Indo-European   Church Slavic, Church Slavonic, Old Church Slavonic, Old Slavonic, Old Bulgarian    ѩзыкъ словѣньскъ    cu  chu chu chu
Afro-Asiatic    Oromo   Afaan Oromoo    om  orm orm orm + 4
Indo-European   Oriya   ଓଡ଼ିଆ   or  ori ori ori
Indo-European   Ossetian, Ossetic   ирон æвзаг  os  oss oss oss
Indo-European   Panjabi, Punjabi    ਪੰਜਾਬੀ  pa  pan pan pan
Indo-European   Pali    पाऴि    pi  pli pli pli
Indo-European   Persian فارسی   fa  fas per fas + 2
Indo-European   Polish  język polski, polszczyzna   pl  pol pol pol
Indo-European   Pashto, Pushto  پښتو    ps  pus pus pus + 3
Indo-European   Portuguese  Português   pt  por por por
Quechuan    Quechua Runa Simi, Kichwa   qu  que que que + 44
Indo-European   Romansh Rumantsch Grischun  rm  roh roh roh
Niger–Congo Rundi   Ikirundi    rn  run run run
Indo-European   Romanian, Moldavian, Moldovan   Română  ro  ron rum ron
Indo-European   Russian русский ru  rus rus rus
Indo-European   Sanskrit    संस्कृतम्   sa  san san san
Indo-European   Sardinian   sardu   sc  srd srd srd + 4
Indo-European   Sindhi  सिन्धी, سنڌي، سندھی‎    sd  snd snd snd
Uralic  Northern Sami   Davvisámegiella se  sme sme sme
Austronesian    Samoan  gagana fa'a Samoa   sm  smo smo smo
Creole  Sango   yângâ tî sängö  sg  sag sag sag
Indo-European   Serbian српски језик    sr  srp srp srp
Indo-European   Gaelic, Scottish Gaelic Gàidhlig    gd  gla gla gla
Niger–Congo Shona   chiShona    sn  sna sna sna
Indo-European   Sinhala, Sinhalese  සිංහල   si  sin sin sin
Indo-European   Slovak  Slovenčina, Slovenský Jazyk sk  slk slo slk
Indo-European   Slovene Slovenski Jezik, Slovenščina    sl  slv slv slv
Afro-Asiatic    Somali  Soomaaliga, af Soomaali so  som som som
Niger–Congo Southern Sotho  Sesotho st  sot sot sot
Indo-European   Spanish, Castilian  Español es  spa spa spa
Austronesian    Sundanese   Basa Sunda  su  sun sun sun
Niger–Congo Swahili Kiswahili   sw  swa swa swa + 2
Niger–Congo Swati   SiSwati ss  ssw ssw ssw
Indo-European   Swedish Svenska sv  swe swe swe
Dravidian   Tamil   தமிழ்   ta  tam tam tam
Dravidian   Telugu  తెలుగు  te  tel tel tel
Indo-European   Tajik   тоҷикӣ, toçikī, تاجیکی‎ tg  tgk tgk tgk
Tai–Kadai   Thai    ไทย th  tha tha tha
Afro-Asiatic    Tigrinya    ትግርኛ    ti  tir tir tir
Sino-Tibetan    Tibetan བོད་ཡིག bo  bod tib bod
Turkic  Turkmen Türkmen, Түркмен    tk  tuk tuk tuk
Austronesian    Tagalog Wikang Tagalog  tl  tgl tgl tgl
Niger–Congo Tswana  Setswana    tn  tsn tsn tsn
Austronesian    Tongan (Tonga Islands)  Faka Tonga  to  ton ton ton
Turkic  Turkish Türkçe  tr  tur tur tur
Niger–Congo Tsonga  Xitsonga    ts  tso tso tso
Turkic  Tatar   татар теле, tatar tele  tt  tat tat tat
Niger–Congo Twi Twi tw  twi twi twi
Austronesian    Tahitian    Reo Tahiti  ty  tah tah tah
Turkic  Uighur, Uyghur  ئۇيغۇرچە‎, Uyghurche    ug  uig uig uig
Indo-European   Ukrainian   Українська  uk  ukr ukr ukr
Indo-European   Urdu    اردو    ur  urd urd urd
Turkic  Uzbek   Oʻzbek, Ўзбек, أۇزبېك‎  uz  uzb uzb uzb + 2
Niger–Congo Venda   Tshivenḓa   ve  ven ven ven
Austroasiatic   Vietnamese  Tiếng Việt  vi  vie vie vie
Constructed Volapük Volapük vo  vol vol vol
Indo-European   Walloon Walon   wa  wln wln wln
Indo-European   Welsh   Cymraeg cy  cym wel cym
Niger–Congo Wolof   Wollof  wo  wol wol wol
Indo-European   Western Frisian Frysk   fy  fry fry fry
Niger–Congo Xhosa   isiXhosa    xh  xho xho xho
Indo-European   Yiddish ייִדיש  yi  yid yid yid + 2
Niger–Congo Yoruba  Yorùbá  yo  yor yor yor
Tai–Kadai   Zhuang, Chuang  Saɯ cueŋƅ, Saw cuengh   za  zha zha zha + 16
Niger–Congo Zulu    isiZulu zu  zul zul zul
'''
