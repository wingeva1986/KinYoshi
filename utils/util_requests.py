import requests
import time
import logging
from requests.exceptions import ConnectTimeout, ConnectionError, SSLError
from lxml import etree

logger = logging.getLogger(__file__)
MAX_RETRY = 3


def send_request(url, headers, method="get", encoding="utf-8", xpath_mode=False, timeout=60, data=None, retry_time=0,
                 stream=False, cookies=None, allow_redirects=True):
    logger.info("==================================================================================")
    logger.info(f"Start request: {url}")
    logger.info(f"      method: {method}")
    logger.info(f"      header: {headers}")
    logger.info(f"      data: {data}")
    logger.info(f"      allow_redirects: {allow_redirects}")
    try:
        if method.lower() == "get":
            response = requests.get(url, params=data, headers=headers, timeout=timeout, stream=stream,
                                    allow_redirects=allow_redirects)
        else:
            if cookies:
                response = requests.post(url, data=data, headers=headers, timeout=timeout, stream=stream,
                                         cookies=cookies, allow_redirects=allow_redirects)
            else:
                response = requests.post(url, data=data, headers=headers, timeout=timeout, stream=stream,
                                         allow_redirects=allow_redirects)
        response.encoding = encoding
    except (ConnectionError, ConnectTimeout, SSLError) as e:
        retry_time += 1
        logging.warning(e)
        if retry_time < MAX_RETRY:
            time.sleep(10)
            return send_request(url, headers, method=method, xpath_mode=xpath_mode, retry_time=retry_time,
                                allow_redirects=allow_redirects)
        else:
            return ""
    else:
        if xpath_mode:
            response = etree.HTML(response.text)
    logger.info(f"End request: {response} - {len(response.text)}")
    logger.info("==================================================================================")
    return response


if __name__ == '__main__':
    print(send_request("http://www.97wowo.com/zy/index.html", {}).text)
