import time

from bs4 import BeautifulSoup
import asyncio
import aiohttp
import csv
import datetime

try:
    from tqdm import tqdm
except (ImportError, ModuleNotFoundError):
    def tqdm(x):
        return x


#  using base_news_path, we will get yielding generator that returns html of each news
#  base_news_path = Formattable string of '{date}/{index}'

# NewsData class contains (date, index, title, content, url)

class NewsData:  # (date, title, content, url)
    def __init__(self, date: str, title: str, content: str, url: str):
        self.date = date
        self.title = title
        self.content = content
        self.url = url

    # Accepts csv writer object, writes data to csv
    def write_to_csv(self, csv_writer: csv.writer):
        csv_writer.writerow([self.date, self.title, self.content, self.url])


class DateNewsIterator:
    # We will get date, index -> generate url.
    # static semaphores
    ASYNC_LOOP = asyncio.get_event_loop()  # we will use this loop for async
    semaphores = asyncio.Semaphore(10)  # only allow 10 concurrent requests

    def __init__(self, base_url: str = '',
                 date: str = "20230405", file_path: str = ""):
        if DateNewsIterator.ASYNC_LOOP.is_closed():
            DateNewsIterator.ASYNC_LOOP = asyncio.new_event_loop()
        self.base_url = base_url
        self.date = date
        self.index = 0
        self.file_path = file_path
        self.save_to_file = False if file_path == "" else True

    async def __aiter__(self):
        return self

    @classmethod
    async def get_html(cls, url: str) -> str:
        async with cls.semaphores:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise ConnectionError('Error')
                    return await response.text()

    async def __anext__(self):
        self.index += 1
        try:
            format_url = self.base_url.format(self.date, self.index)
            request_result = await DateNewsIterator.get_html(format_url)
            parsed_result = await self.parse(request_result, format_url)  # self.parse -> None | NewsData
            if parsed_result is None:
                raise StopAsyncIteration
            return parsed_result
        except ConnectionError:
            raise StopAsyncIteration

    async def parse(self, text: str, url: str = "") -> NewsData | None:
        soup = BeautifulSoup(text, 'html.parser')
        # title : <meta property="og:title" content="$content">
        # content : <meta property="og:description" content="$content">
        # we don't modify date even if there were fixes for content
        title = soup.find('meta', property='og:title')
        if title is None:
            return None
        title = title['content']
        contents = soup.find_all('meta', property='og:description')
        if contents is None:
            merged_string = ""
        else:
            merged_string = ""
            for content in contents:
                merged_string += content['content']
        return NewsData(self.date, title, merged_string, url)

    @classmethod
    def get_all(cls, date: str = '20230405') -> list:
        iterator = cls(date=date)
        results = []
        try:
            while True:
                result = cls.ASYNC_LOOP.run_until_complete(iterator.__anext__())
                results.append(result)
        except (StopIteration, StopAsyncIteration):
            return results
        finally:
            return results

    def __iter__(self):
        try:
            while True:
                yield DateNewsIterator.ASYNC_LOOP.run_until_complete(self.__anext__())
        except (StopIteration, StopAsyncIteration):
            return

    @classmethod
    async def get_all_async(cls, date: str = '20230405') -> list:
        iterator = cls(date=date)
        results = []
        try:
            while True:
                result = await iterator.__anext__()
                results.append(result)
        except (StopIteration, StopAsyncIteration):
            return results
        finally:
            return results

    async def save_to_csv(self, file_path: str = 'news.csv'):
        with open(file_path, 'w', newline='') as f:
            csvWriter = csv.writer(f)
            csvWriter.writerow(['date', 'index', 'title', 'content', 'url'])
            async for i in self:
                i.write_to_csv(csvWriter)

    def save_to_csv_sync(self, file_path: str = 'news.csv'):
        with open(file_path, 'w', newline='') as f:
            csvWriter = csv.writer(f)
            csvWriter.writerow(['date', 'index', 'title', 'content', 'url'])
            for i in self:
                i.write_to_csv(csvWriter)

    def save_to_writer_sync(self, csv_writer: csv.writer = None):
        for i in self:
            i.write_to_csv(csv_writer)

    async def save_to_writer_async(self, csv_writer: csv.writer = None):
        async for i in self:
            i.write_to_csv(csv_writer)

    @classmethod
    def set_semaphore(cls, semaphore: int):
        cls.semaphores = asyncio.Semaphore(semaphore)


class DateRangeIterator:
    # A set of DateNewsIterator
    # We will get (start_date, end_date) -> generate DateNewsIterator
    # implements __iter__ and __next__ -> we can use for loop
    # implements __aiter__ and __anext__ -> we can use async for loop

    def __init__(self, base_url: str = "", start_date: int = 20230403, end_date: int = 20230405, file_path: str = ""):
        self.start_date = start_date
        self.end_date = end_date
        self.base_url = base_url
        self.date_generator = get_date_genexpr(start_date, end_date)
        self.date_count = get_date_count(start_date, end_date)
        self.current_date = start_date
        self.current_index = 0
        self.file_path = file_path

    def __iter__(self):
        return self

    def __next__(self) -> DateNewsIterator:
        if self.current_index > self.date_count:
            raise StopIteration
        self.current_index += 1
        self.current_date = next(self.date_generator)
        return DateNewsIterator(base_url=self.base_url, date=str(self.current_date), file_path=self.file_path)

    def __len__(self):
        return self.date_count


def get_date_genexpr(start_date, end_date):
    start_date = datetime.datetime.strptime(str(start_date), '%Y%m%d')
    end_date = datetime.datetime.strptime(str(end_date), '%Y%m%d')
    for i in range((end_date - start_date).days + 1):
        yield (start_date + datetime.timedelta(days=i)).strftime('%Y%m%d')


def get_current_date() -> str:
    return datetime.datetime.now().strftime('%Y%m%d')


def get_date_count(start_date, end_date) -> int:
    start_date = datetime.datetime.strptime(str(start_date), '%Y%m%d')
    end_date = datetime.datetime.strptime(str(end_date), '%Y%m%d')
    return (end_date - start_date).days


#  DateNewsIterator(date = '20230405') -> NewsData(date, index, title, content, url)
if __name__ == "__main__":
    FILE_PATH = "news.csv"  # csv to write. environment may not have pandas, so we will use csv
    SLEEP_TIME = 1  # we will sleep for 1 second to prevent server from blocking us
    START_DATE = 20220904  # page 72 date
    END_DATE = 20230405
    URL_FORMAT = ""
    # date_end = 20230405 or current date
    print(f"Start date : {START_DATE}, End date : {END_DATE}")
    print(f"Total date count : {get_date_count(str(START_DATE), END_DATE)}")
    iteratorSet = DateRangeIterator(base_url=URL_FORMAT,
                                    start_date=START_DATE, end_date=int(END_DATE), file_path=FILE_PATH)
    DateNewsIterator.set_semaphore(10)  # we will allow 10 concurrent requests
    with open(FILE_PATH, 'w', newline='') as f:
        writer = csv.writer(f)
        for iterator in tqdm(iteratorSet):
            iterator.save_to_writer_sync(csv_writer=writer)
            time.sleep(SLEEP_TIME)  # Prevent server from blocking us

    # NOTE : We don't use selenium, so the result may be incorrect or pruned
    # But I think it's enough to get the news title data
