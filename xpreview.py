import discord
from discord.ext import commands
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
from io import BytesIO
import re
import asyncio
import time

intents = discord.Intents.all()
bot: commands.Bot = commands.Bot(command_prefix='!', intents=intents)

analysis_queue: asyncio.Queue[[str, int, int]] = asyncio.Queue()

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

async def isLoadedAllImages(driver: webdriver.Chrome, timeOut: int = 300, interval: float = 0.1) -> bool:
  completed: bool = False
  start: float = time.time()
  while time.time() - start < timeOut and completed == False:
    completed = driver.execute_script(JavaScriptIsLoadedAllImagesCall)
    await asyncio.sleep(interval)
  return completed

async def get_tweet_image() -> None:
    options: webdriver.FirefoxOptions = webdriver.ChromeOptions()
    options.headless = True

    driver: webdriver.Firefox = webdriver.Chrome(options=options)

    wait: WebDriverWait = WebDriverWait(driver, 10)  # wait up to 10 seconds for elements to appear

    while True:
        url, channel_id, message_id = await analysis_queue.get()
        message: discord.Message = await bot.get_channel(channel_id).fetch_message(message_id)

        driver.get(url)
        driver.execute_script(JavaScriptIsLoadedAllImagesDefine)

        try:
            # ツイートの要素が表示されるまで待機する
            element = wait.until(EC.presence_of_element_located((By.XPATH, "//article[@data-testid='tweet']")))
        except:
            # ツイートの要素が表示されなかった場合は、取得失敗としてメッセージを更新する
            await message.edit(content="取得失敗")
            continue

        # ページ内のすべての画像が読み込まれるまで待機する
        await isLoadedAllImages(driver)

        # ツイートのスクリーンショットを取得する
        png: bytes = element.screenshot_as_png

        im: Image.Image = Image.open(BytesIO(png))

        with BytesIO() as image_binary:
            im.save(image_binary, 'PNG')
            image_binary.seek(0)
            file: discord.File = discord.File(fp=image_binary, filename='tweet.png')

        # メッセージにスクリーンショットを添付する
        if not message.attachments:
            await message.edit(content=None, attachments=[file])
        else:
            await message.add_files(file)

bot.run('MTE2ODYwMDE4MTQ0NTUwOTE2MA.GLmMbm.U4GVb3o2BB_RFxJ8BFDcngWZIIP1Tx9tmyjBSQ')