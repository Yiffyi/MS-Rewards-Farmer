import dbm.dumb
import logging
import shelve
from enum import Enum, auto
from random import random, randint
from time import sleep
from typing import Final

from selenium.webdriver.common.by import By
from trendspy import Trends

from src.browser import Browser
from src.utils import CONFIG, getProjectRoot, cooldown, COUNTRY, makeRequestsSession
import requests


class RetriesStrategy(Enum):
    """
    method to use when retrying
    """

    EXPONENTIAL = auto()
    """
    an exponentially increasing `backoff-factor` between attempts
    """
    CONSTANT = auto()
    """
    the default; a constant `backoff-factor` between attempts
    """


class CNSearches:
    """
    Class to handle CN specific trending searches in MS Rewards.
    """

    maxRetries: Final[int] = CONFIG.retries.max
    """
    the max amount of retries to attempt
    """

    trendingItems: list

    def __init__(self, browser: Browser):
        self.browser = browser
        self.webdriver = browser.webdriver

    def __enter__(self):
        logging.debug("[CNSearches] __enter__")
        response = makeRequestsSession().get(
            "https://cn.bing.com/hp/api/v1/carousel?=&format=json&ecount=24&efirst=0&FORM=BEHPTB&setlang=zh-Hans"
        )
        if response.status_code != requests.codes.ok:
            raise requests.HTTPError(
                f"Failed to fetch cn.bing.com search trending. "
                f"Status code: {response.status_code}"
            )
        j = response.json()
        assert j["statusCode"] == 200
        data = j["data"][0]
        assert data["typeName"] == "TrendingNow"
        # "items": [
        #     {
        #         "title": "结婚离婚不用户口本",
        #         "url": "/search?q=%e7%bb%93%e5%a9%9a%e7%a6%bb%e5%a9%9a%e4%b8%8d%e7%94%a8%e6%88%b7%e5%8f%a3%e6%9c%ac&efirst=0&ecount=50&filters=tnTID%3a%22DSBOS_1AFDFAD0F5EF45FB865544E58DB7F801%22+tnVersion%3a%2243b28438849f4902ad7261f596293f27%22+Segment%3a%22popularnow.carousel%22+tnCol%3a%220%22+tnOrder%3a%227ee05f48-63ce-4b78-9daf-9b74bc689784%22&form=HPNN01",
        #         "imageUrl": "/th?id=OVFT.AOt2tw9kmOZX0rHrXp-n0y&w=186&h=88&c=7&rs=2&qlt=80&pid=PopNow",
        #         "badge": null,
        #         "imageCredit": "",
        #         "tooltip": "结婚离婚不用户口本",
        #         "linksTarget": "",
        #         "dataTags": null,
        #         "additionalMetaData": null,
        #         "shortTitle": "",
        #         "longTitle": "",
        #         "tag": "Hot"
        #     },
        # ]
        import random

        self.trendingItems = data["items"]
        random.shuffle(self.trendingItems)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.debug("[CNSearches] __exit__")

    def bingSearches(self) -> None:
        # Function to perform Bing searches
        logging.info(
            f"[BING] Starting {self.browser.browserType.capitalize()} Edge Bing searches..."
        )

        self.browser.utils.goToSearch()

        for trend in self.trendingItems:
            desktopAndMobileRemaining = self.browser.getRemainingSearches(
                desktopAndMobile=True
            )
            logging.info(f"[BING] Remaining searches={desktopAndMobileRemaining}")
            if (
                self.browser.browserType == "desktop"
                and desktopAndMobileRemaining.desktop == 0
            ) or (
                self.browser.browserType == "mobile"
                and desktopAndMobileRemaining.mobile == 0
            ):
                break

            self.bingSearch(trend)
            sleep(randint(10, 15))

        logging.info(
            f"[BING] Finished {self.browser.browserType.capitalize()} Edge Bing searches !"
        )

    def bingSearch(self, trendingItem) -> None:
        # Function to perform a single Bing search
        pointsBefore = self.browser.utils.getAccountPoints()

        logging.debug(f"trendingItem={trendingItem}")
        logging.debug(f"trendKeywords={trendingItem["title"]}")
        from urllib.parse import urljoin

        for i in range(self.maxRetries + 1):

            self.webdriver.get(urljoin("https://cn.bing.com/", trendingItem["url"]))
            cooldown()

            pointsAfter = self.browser.utils.getAccountPoints()
            if pointsBefore < pointsAfter:
                return

            logging.debug(
                f"[BING] Search attempt not counted {i}/{Searches.maxRetries}, before={pointsBefore}, after={pointsAfter}"
            )
            # todo
            # if i == (maxRetries / 2):
            #     logging.info("[BING] " + "TIMED OUT GETTING NEW PROXY")
            #     self.webdriver.proxy = self.browser.giveMeProxy()
        logging.error("[BING] Reached max search attempt retries")


class Searches:
    """
    Class to handle searches in MS Rewards.
    """

    maxRetries: Final[int] = CONFIG.retries.max
    """
    the max amount of retries to attempt
    """
    baseDelay: Final[float] = CONFIG.get("retries.backoff-factor")
    """
    how many seconds to delay
    """
    # retriesStrategy = Final[  # todo Figure why doesn't work with equality below
    retriesStrategy = RetriesStrategy[CONFIG.retries.strategy]

    def __init__(self, browser: Browser):
        self.browser = browser
        self.webdriver = browser.webdriver

        dumbDbm = dbm.dumb.open((getProjectRoot() / "google_trends").__str__())
        self.googleTrendsShelf: shelve.Shelf = shelve.Shelf(dumbDbm)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.googleTrendsShelf.__exit__(None, None, None)

    def bingSearches(self) -> None:
        # Function to perform Bing searches
        logging.info(
            f"[BING] Starting {self.browser.browserType.capitalize()} Edge Bing searches..."
        )

        self.browser.utils.goToSearch()

        while True:
            desktopAndMobileRemaining = self.browser.getRemainingSearches(
                desktopAndMobile=True
            )
            logging.info(f"[BING] Remaining searches={desktopAndMobileRemaining}")
            if (
                self.browser.browserType == "desktop"
                and desktopAndMobileRemaining.desktop == 0
            ) or (
                self.browser.browserType == "mobile"
                and desktopAndMobileRemaining.mobile == 0
            ):
                break

            if desktopAndMobileRemaining.getTotal() > len(self.googleTrendsShelf):
                logging.debug(
                    f"google_trends before load = {list(self.googleTrendsShelf.items())}"
                )
                trends = Trends()
                trends = trends.trending_now(geo=COUNTRY)[
                    : desktopAndMobileRemaining.getTotal()
                ]
                for trend in trends:
                    self.googleTrendsShelf[trend.keyword] = trend
                logging.debug(
                    f"google_trends after load = {list(self.googleTrendsShelf.items())}"
                )

            self.bingSearch()
            sleep(randint(10, 15))

        logging.info(
            f"[BING] Finished {self.browser.browserType.capitalize()} Edge Bing searches !"
        )

    def bingSearch(self) -> None:
        # Function to perform a single Bing search
        pointsBefore = self.browser.utils.getAccountPoints()

        trend = list(self.googleTrendsShelf.keys())[0]
        trendKeywords = self.googleTrendsShelf[trend].trend_keywords
        logging.debug(f"trendKeywords={trendKeywords}")
        logging.debug(f"trend={trend}")
        baseDelay = Searches.baseDelay

        for i in range(self.maxRetries + 1):
            if i != 0:
                if not trendKeywords:
                    del self.googleTrendsShelf[trend]

                    trend = list(self.googleTrendsShelf.keys())[0]
                    trendKeywords = self.googleTrendsShelf[trend].trend_keywords

                sleepTime: float
                if Searches.retriesStrategy == Searches.retriesStrategy.EXPONENTIAL:
                    sleepTime = baseDelay * 2 ** (i - 1)
                elif Searches.retriesStrategy == Searches.retriesStrategy.CONSTANT:
                    sleepTime = baseDelay
                else:
                    raise AssertionError
                sleepTime += baseDelay * random()  # Add jitter
                logging.debug(
                    f"[BING] Search attempt not counted {i}/{Searches.maxRetries},"
                    f" sleeping {sleepTime}"
                    f" seconds..."
                )
                sleep(sleepTime)

            self.browser.utils.goToSearch()
            searchbar = self.browser.utils.waitUntilClickable(
                By.ID, "sb_form_q", timeToWait=40
            )
            searchbar.clear()
            trendKeyword = trendKeywords.pop(0)
            logging.debug(f"trendKeyword={trendKeyword}")
            sleep(1)
            searchbar.send_keys(trendKeyword)
            sleep(1)
            searchbar.submit()

            pointsAfter = self.browser.utils.getAccountPoints()
            if pointsBefore < pointsAfter:
                del self.googleTrendsShelf[trend]
                cooldown()
                return

            # todo
            # if i == (maxRetries / 2):
            #     logging.info("[BING] " + "TIMED OUT GETTING NEW PROXY")
            #     self.webdriver.proxy = self.browser.giveMeProxy()
        logging.error("[BING] Reached max search attempt retries")
