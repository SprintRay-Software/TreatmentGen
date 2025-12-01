import sys

import aiohttp
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

HEADERS = {"Content-Type": "application/json"}


class APIClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def generate(
        self,
        prompt: str,
        model_name: str,
        api_base: str,
        max_tokens: int = 2048,
        temperature: float = 0.6,
        top_p: float = 1.0,
        repetition_penalty: float = 1.0,
    ) -> str | None:
        endpoint = f"{api_base}/v1/chat/completions"
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "repetition_penalty": repetition_penalty,
        }

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=4, max=10),
            ):
                with attempt:
                    async with self.session.post(
                        endpoint,
                        headers=HEADERS,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=300),
                    ) as resp:
                        if resp.status == 200:
                            response = await resp.json()
                            content = response["choices"][0]["message"]["content"]
                            return content
                        else:
                            error_text = await resp.text()
                            print(
                                f"API 错误 ({resp.status}): {error_text}",
                                file=sys.stderr,
                            )
                            raise Exception(f"API 返回错误: {resp.status}")
        except Exception as e:
            print(f"生成失败: {e}", file=sys.stderr)
            return None
