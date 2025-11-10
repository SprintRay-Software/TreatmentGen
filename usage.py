import asyncio
import json
import os
import time

import aiohttp

from app.core.logger import logger

TOKEN_ID = ""
TOKEN_SECRET = ""
APP_URL = ""
HEADERS = {
    "Content-Type": "application/json",
    "Modal-Key": TOKEN_ID,
    "Modal-Secret": TOKEN_SECRET,
}


async def test(session, data, sem):
    # with open("./data/panoramic_1300.json", encoding="utf-8") as fp:
    #     data = json.load(fp)
    async with sem:
        async with aiohttp.ClientSession() as session:
            async with session.post(APP_URL, headers=HEADERS, json=data) as resp:
                resp.raise_for_status()
                try:
                    result = await resp.json()
                    logger.info(f"Result: {result}")
                except json.JSONDecodeError as e:
                    result = await resp.text()
                    logger.error(f"Failed to decode JSON: {e}. Raw response: {result}")
                result = await resp.json()

                return result


async def batch_test(input_dir):
    batch_data = []
    for filename in sorted(os.listdir(input_dir)):
        filepath = os.path.join(input_dir, filename)
        if os.path.isfile(filepath) and filename.endswith(".json"):
            with open(filepath, encoding="utf-8") as fp:
                batch_data.append(json.load(fp))

    start = time.time()
    semaphore = asyncio.Semaphore(1)
    async with aiohttp.ClientSession() as session:
        tasks = [test(session, data, semaphore) for data in batch_data]
        _ = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.time() - start
    logger.info(f"Time taken: {elapsed:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(batch_test("./data"))
