import os

import io
import scrapy
from scrapy import Request
from scrapy import signals

from fooltrader import settings
from fooltrader.consts import DEFAULT_TICK_HEADER
from fooltrader.contract.files_contract import get_tick_path_csv
from fooltrader.utils.utils import get_trading_dates, is_available_tick, get_datetime, get_kdata_item_with_date, \
    kdata_to_tick, get_security_items, sina_tick_to_csv


class StockTickSpider(scrapy.Spider):
    name = "stock_tick"

    custom_settings = {
        'DOWNLOAD_DELAY': 1,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 8,

        'SPIDER_MIDDLEWARES': {
            'fooltrader.middlewares.FoolErrorMiddleware': 1000,
        }
    }

    def yield_request(self, item, trading_dates=None):
        if not trading_dates:
            trading_dates = get_trading_dates(item)

        for trading_date in trading_dates:
            if get_datetime(trading_date) < get_datetime(settings.START_TICK_DATE) or get_datetime(
                    trading_date) < get_datetime(settings.AVAILABLE_TICK_DATE):
                continue
            path = get_tick_path_csv(item, trading_date)

            if os.path.isfile(path) and is_available_tick(path):
                continue
            yield Request(url=self.get_tick_url(trading_date, item['exchange'] + item['code']),
                          meta={'proxy': None,
                                'path': path,
                                'trading_date': trading_date,
                                'item': item},
                          headers=DEFAULT_TICK_HEADER,
                          callback=self.download_tick)

    def start_requests(self):
        item = self.settings.get("security_item")
        trading_dates = self.settings.get("trading_dates")
        if item:
            for request in self.yield_request(item, trading_dates):
                yield request
        else:
            for item in get_security_items():
                for request in self.yield_request(item):
                    yield request

    def download_tick(self, response):
        content_type_header = response.headers.get('content-type', None)
        if content_type_header.decode("utf-8") == 'application/vnd.ms-excel' or "当天没有数据" in response.body.decode(
                'GB2312'):
            trading_date = response.meta['trading_date']
            security_item = response.meta['item']
            if content_type_header.decode("utf-8") == 'application/vnd.ms-excel':
                content = response.body
            else:
                kdata_json = get_kdata_item_with_date(security_item, trading_date)
                content = kdata_to_tick(response.meta['item'], kdata_json).encode('GB2312')
            sina_tick_to_csv(security_item, io.BytesIO(content), trading_date)
        else:
            self.logger.error(
                "get tick error:url={} content type={} body={}".format(response.url, content_type_header,
                                                                       response.body))

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(StockTickSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def spider_closed(self, spider, reason):
        spider.logger.info('Spider closed: %s,%s\n', spider.name, reason)

    def get_tick_url(self, date, code):
        return 'http://market.finance.sina.com.cn/downxls.php?date={}&symbol={}'.format(date, code)
