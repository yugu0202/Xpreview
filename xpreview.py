from typing import Optional, Any, List

import discord
from discord.ext import commands
from discord.enums import ButtonStyle
from discord.interactions import Interaction
from discord.ui import Button, View

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from PIL import Image
from io import BytesIO
import re
import asyncio
import time
import sqlite3
import os
from os.path import join, dirname
from dotenv import load_dotenv

class RetryButton(Button):
    def __init__(self, *, style: ButtonStyle = ButtonStyle.primary, label: Optional[str] = None, disabled: bool = False, custom_id: Optional[str] = None, row: Optional[int] = None, func: Any = None) -> None:
        super().__init__(style=style, label=label,
                         disabled=disabled, custom_id=custom_id, row=row)
        self.func: Any = func

    async def callback(self, interaction: Interaction) -> Any:
        return await self.func(interaction)


class RetryAnalysisView(View):
    def __init__(self, *, url: str = None, timeout=None) -> None:
        super().__init__(timeout=timeout)
        self.url: str = url

        self.retry_button: RetryButton = RetryButton(
            style=ButtonStyle.red,
            label="再取得",
            custom_id="retry",
            func=self.retry
        )

        self.add_item(self.retry_button)

    async def retry(self, interaction: Interaction) -> None:
        await interaction.response.edit_message(content="取得中...", view=None)
        await analysis_queue.put([self.url, interaction.channel.id, interaction.message.id])

load_dotenv(verbose=True)
dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

intents = discord.Intents.all()
bot: commands.Bot = commands.Bot(command_prefix='!', intents=intents)

analysis_queue = asyncio.Queue()

# JavaScriptで、ページ内のすべての画像が読み込まれたかどうかを判定する関数を定義する
JavaScriptIsLoadedImagesDefine: str = " \
window.isLoadedAllImages = () => { \
  const images = document.getElementsByTagName('article')[0].getElementsByTagName('img'); \
  let completed = true; \
  for (const image of images) { \
    if (image.complete === false) { \
      completed = false; \
      break; \
    } \
  } \
  return completed; \
}"

# JavaScriptで、ページ内のすべての画像が読み込まれたかどうかを判定する関数を呼び出すコードを定義する
JavaScriptIsLoadedImagesCall: str = "return isLoadedAllImages();"


@bot.event
async def on_ready() -> None:
    print(f'{bot.user.name} has connected to Discord!')
    asyncio.ensure_future(get_tweet_image())


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author == bot.user:
        return

    urls: List[str] = re.findall("(?P<url>https?://[^\s]+)", message.content)

    urls = [url for url in urls if "twitter.com" in url or "x.com" in url]

    if urls:
        message = await message.reply("取得中...", mention_author=False)

        for url in urls:
            await analysis_queue.put([url, message.channel.id, message.id])

    await bot.process_commands(message)


async def isLoadedAllImages(driver: Chrome, timeOut: int = 300, interval: float = 0.1) -> bool:
    completed: bool = False
    start: float = time.time()
    while time.time() - start < timeOut and completed == False:
        completed = driver.execute_script(JavaScriptIsLoadedImagesCall)
        await asyncio.sleep(interval)
    return completed


async def get_tweet_image() -> None:
    service = Service('./chromedriver-linux64/chromedriver')
    options: ChromeOptions = ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')  # 暫定的に必要なフラグとのこと
    options.add_argument('--window-size=4096x2160')  # ウィンドウサイズを指定
    options.add_argument('--lang=ja-JP')
    options.add_experimental_option(
        'prefs', {'intl.accept_languages': 'ja,jp'})

    driver: Chrome = Chrome(
        service=service, options=options)

    # wait up to 10 seconds for elements to appear
    wait: WebDriverWait = WebDriverWait(driver, 10)

    while True:
        url, channel_id, message_id = await analysis_queue.get()
        message: discord.Message = await bot.get_channel(channel_id).fetch_message(message_id)

        driver.get(url)
        driver.execute_script(JavaScriptIsLoadedImagesDefine)

        try:
            # ツイートの要素が表示されるまで待機する
            element = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//article[@data-testid='tweet']")))
        except:
            # ツイートの要素が表示されなかった場合は、取得失敗としてメッセージを更新する
            view: RetryAnalysisView = RetryAnalysisView(url=url)
            await message.edit(content="取得失敗", view=view)
            continue

        # ページ内のすべての画像が読み込まれるまで待機する
        await isLoadedAllImages(driver)

        # ツイートのスクリーンショットを取得する
        png: bytes = element.screenshot_as_png

        im: Image.Image = Image.open(BytesIO(png))

        with BytesIO() as image_binary:
            im.save(image_binary, 'PNG')
            image_binary.seek(0)
            file: discord.File = discord.File(
                fp=image_binary, filename='tweet.png')

        # メッセージにスクリーンショットを添付する
        await message.edit(content=None, attachments=[file])

bot.run(os.environ['DISCORD_TOKEN'])
