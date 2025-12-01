import asyncio
import json
import os
import time
from typing import Any

import aiohttp
from langfuse import Langfuse, observe
from vllm import LLM, SamplingParams

from app.client import APIClient
from app.core.logger import logger
from app.prompt.draft import DRAFT_PROMPT
from app.prompt.example import INPUT_EXAMPLE, OUTPUT_EXAMPLE
from app.prompt.revision import REVISION_PROMPT

schema = {
    "type": "object",
    "oneOf": [
        {
            "properties": {"need revision": {"const": False}},
            "required": ["need revision"],
            "additionalProperties": False,
        },
        {
            "properties": {
                "need revision": {"const": True},
                "Revised med report": {
                    "type": "object",
                    "properties": {
                        "Revised Report": {"type": "string"},
                        "Revision Log": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["Revised Report", "Revision Log"],
                    "additionalProperties": False,
                },
            },
            "required": ["need revision", "Revised med report"],
            "additionalProperties": False,
        },
    ],
}


class TreatmentService:
    def __init__(
        self,
        llm: LLM | None = None,
        sampling_params: SamplingParams | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
    ):
        self.llm = llm
        self.sampling_params = sampling_params
        self.model_name = model_name
        self.base_url = base_url

    @observe(as_type="generation")
    def offline_inference(self, prompt: str, label: str | None = None) -> str:
        tokenizer = self.llm.get_tokenizer()
        messages = [{"role": "user", "content": prompt}]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        if label == "revision":
            from vllm.sampling_params import StructuredOutputsParams

            self.sampling_params.structured_outputs = StructuredOutputsParams(
                json=schema,
                disable_additional_properties=True,
            )
        else:
            self.sampling_params.structured_outputs = None

        outputs = self.llm.generate([prompt], self.sampling_params)
        text = outputs[0].outputs[0].text
        parts = text.split("</think>", 1)

        return (parts[1] if len(parts) == 2 else text).strip()

    @observe(as_type="generation")
    async def online_inference(self, prompt: str) -> str:
        async with aiohttp.ClientSession() as session:
            client = APIClient(session=session)
            response = await client.generate(
                prompt=prompt,
                model_name=self.model_name,
                api_base=self.base_url,
            )
            return response

    async def treatment_generate(
        self,
        sample: dict[str, Any],
        semaphore: asyncio.Semaphore,
        langfuse: Langfuse,
    ) -> dict[str, Any]:
        async with semaphore:
            draft_prompt = DRAFT_PROMPT.format(
                input_example=INPUT_EXAMPLE,
                output_example=OUTPUT_EXAMPLE,
                input=sample["caption"],
            )
            # draft_body = await self.online_inference(draft_prompt)
            draft_body = await asyncio.to_thread(self.offline_inference, draft_prompt)
            if draft_body:
                logger.info("Draft 内容生成成功")
            else:
                logger.error("Draft 内容生成失败")
                raise Exception("Draft 内容生成失败")

            refined_prompt = REVISION_PROMPT + "\n" + draft_body
            # refined_body = await self.online_inference(refined_prompt)
            refined_body = await asyncio.to_thread(
                self.offline_inference, prompt=refined_prompt, label="revision"
            )
            if refined_body:
                logger.info("Refined 内容生成成功")
            else:
                logger.error("Refined 内容生成失败")
                raise Exception("Refined 内容生成失败")

            refined_body = json.loads(
                refined_body.replace("```json", "").replace("```", "").strip()
            )

            treatment_client = langfuse.get_prompt("treatment_en", label="latest")
            TREATMENT_PROMPT = treatment_client.compile()

            if refined_body.get("need revision"):
                report_content = refined_body.get("Revised med report").get("Revised Report")
                treatment_prompt = TREATMENT_PROMPT.format(report=report_content)
            else:
                report_content = draft_body
                treatment_prompt = TREATMENT_PROMPT.format(report=draft_body)

            with langfuse.start_as_current_observation(
                as_type="generation",
                name="treatment_generation",
                model=self.model_name or "unknown",
                model_parameters={
                    "max_tokens": 2048,
                    "temperature": 0.6,
                    "top_p": 1.0,
                    "repetition_penalty": 1.0,
                },
                input={"report": report_content},
                prompt=treatment_client,
            ) as generation:
                # treatment_body = await self.online_inference(treatment_prompt)
                treatment_body = await asyncio.to_thread(self.offline_inference, treatment_prompt)

                if treatment_body:
                    logger.info("Treatment 内容生成成功")
                else:
                    logger.error("Treatment 内容生成失败")
                    raise Exception("Treatment 内容生成失败")

                generation.update(output=treatment_body)

            return {
                "id": sample["id"],
                "treatment": treatment_body,
            }

    async def batch_treatment_generate(
        self,
        captions: list[dict[str, Any]],
        treatment_out_dir: str,
        langfuse: Langfuse,
        max_concurrent: int = 10,
    ) -> list[dict[str, Any]]:
        start = time.time()
        semaphore = asyncio.Semaphore(max_concurrent)

        tasks = [self.treatment_generate(sample, semaphore, langfuse) for sample in captions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        os.makedirs(treatment_out_dir, exist_ok=True)
        treatments = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"生成失败: {result}")
                continue

            output_path = os.path.join(treatment_out_dir, f"treatment_{result['id']}.md")
            with open(output_path, "w", encoding="utf-8") as fp:
                fp.write(result["treatment"])

            treatments.append(
                {
                    "id": result["id"],
                    "treatment": result["treatment"],
                }
            )

        elapsed = time.time() - start
        logger.info(f"生成完成，耗时: {elapsed:.2f} 秒")

        return treatments
