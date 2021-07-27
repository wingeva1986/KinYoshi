# coding=utf-8
import logging
import os

from flask import Flask, request, jsonify, make_response

from legendei_subtitle_server.legendei import Legendei

logger = logging.getLogger("legendei_subtitle_server")
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
app = Flask(__name__)


@app.route('/legendei/api/v1/subtitle_search', methods=['GET'])
def subtitle_search_for_legendei():
    logger.info('request.args=%s', request.args)
    logger.info('request.headers=%s', request.headers)
    keyword = request.args.get('keyword')

    res = {'status': 400, 'result': 'error'}
    if not not keyword:
        res['status'] = 200
        legendei = Legendei()
        result = legendei.subtitle_search(keyword)
        res['result'] = result
    return jsonify(res)


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


if __name__ == '__main__':
    pid = os.getpid()
    pid_file = os.path.join('log', 'pid')
    with open(pid_file, 'w') as f:
        f.write(str(pid))
    app.run(host='0.0.0.0', port=9797, debug=False)