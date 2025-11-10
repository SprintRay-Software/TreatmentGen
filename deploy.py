import os
from typing import Any

import modal
from vllm import LLM, SamplingParams

from app.core.logger import logger

MINUTES = 60
CPU = 16.0
MEMORY = 32000
MAX_MODEL_LEN = 8192
N_GPU = 1
FAST_BOOT = True
MODEL_NAME = "lingshu-medical-mllm/Lingshu-7B"
MODEL_REVISION = "b98aecd41dfd9d7545a6b8e2f4743ae8471bd7a9"

hf_cache_vol = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache", create_if_missing=True)
output_cache_col = modal.Volume.from_name("output-cache", create_if_missing=True)


TREATMENT_OUTPUT_DIR = "/output/treatments"
CAPTION_OUTPUT_DIR = "/output/captions"
volumes = {
    "/root/.cache/huggingface": hf_cache_vol,
    "/root/.cache/vllm": vllm_cache_vol,
    "/output": output_cache_col,
}

cuda_version = "12.8.0"
flavor = "devel"
operating_sys = "ubuntu22.04"
tag = f"{cuda_version}-{flavor}-{operating_sys}"
snap = False


def download_model():
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=MODEL_NAME,
        revision=MODEL_REVISION,
        ignore_patterns=["*.pt", "*.bin"],
    )


image = (
    modal.Image.from_registry(f"nvidia/cuda:{tag}", add_python="3.12")
    .env({"CUDA_HOME": "/usr/local/cuda"})
    .env({"PATH": "${CUDA_HOME}/bin:${PATH}"})
    .env({"LD_LIBRARY_PATH": "${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}"})
    .run_commands("apt-get update")
    .apt_install(["build-essential", "cmake"])
    .run_commands("apt-get clean")
    .run_commands("rm -rf /var/lib/apt/lists/*")
    .pip_install(
        "vllm==0.11.0",
        "torch==2.8.0",
        "flashinfer-python==0.3.1",
        "aiohttp>=3.13.1",
        "loguru>=0.7.3",
        "hf-xet==1.1.5",
        "tenacity>=9.1.2",
        "langfuse>=3.9.1",
        "fastapi[standard]>=0.121.0",
        "huggingface_hub[hf_transfer]==0.35.0",
    )
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
        }
    )
    .add_local_dir("app", remote_path="/root/app", copy=True)
    .run_function(download_model, volumes=volumes)
)

app = modal.App("treatment-generation")


@app.cls(
    image=image,
    cpu=CPU,
    memory=MEMORY,
    gpu=f"L40S:{N_GPU}",
    enable_memory_snapshot=snap,
    experimental_options={"enable_gpu_snapshot": snap},
    scaledown_window=3 * MINUTES,
    timeout=10 * MINUTES,
    volumes=volumes,
    secrets=[modal.Secret.from_name("langfuse")],
)
@modal.concurrent(max_inputs=3)
class Modal:
    @modal.enter(snap=snap)
    def start(self) -> None:
        from langfuse import Langfuse

        from app.core.logger import logger
        from app.service.caption_service import CaptionService
        from app.service.treatment_service import TreatmentService

        logger.info(f"初始化 vLLM 引擎: {MODEL_NAME}")

        self.llm = LLM(
            model=MODEL_NAME,
            revision=MODEL_REVISION,
            max_model_len=MAX_MODEL_LEN,
            tensor_parallel_size=N_GPU,
            enforce_eager=FAST_BOOT,
            gpu_memory_utilization=0.8,
            trust_remote_code=True,
        )

        self.sampling_params = SamplingParams(
            temperature=0.7,
            top_p=1,
            repetition_penalty=1,
            max_tokens=2048,
            stop_token_ids=[],
        )

        logger.info("vLLM 引擎初始化完成")

        self.treatment_service = TreatmentService(
            llm=self.llm,
            sampling_params=self.sampling_params,
        )
        self.caption_service = CaptionService()

        langfuse = Langfuse(
            public_key=os.getenv("public_key"),
            secret_key=os.getenv("secret_key"),
            base_url=os.getenv("host"),
        )

        if langfuse.auth_check():
            logger.info("Langfuse 认证成功")
        else:
            logger.error("Langfuse 认证失败")

    @modal.exit()
    def shuntdown(self) -> None:
        from langfuse import get_client

        logger.info("释放 vLLM & Langfuse 资源")

        del self.llm
        del self.sampling_params

        langfuse = get_client()
        langfuse.shutdown()

    @modal.fastapi_endpoint(method="GET", requires_proxy_auth=True)
    def health(self) -> dict[str, str]:
        _ = self.llm.generate(["hi"], SamplingParams(max_tokens=1, temperature=0.0))
        logger.info("vLLM 引擎热身完成")

        return {"status": 200}

    @modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
    async def generate(
        self,
        payload: dict[str, Any] | list[dict[str, Any]],
        treatment_out_dir: str = TREATMENT_OUTPUT_DIR,
        caption_out_dir: str = CAPTION_OUTPUT_DIR,
    ) -> list[dict[str, Any]]:
        captions = self.caption_service.batch_caption_generate(payload, caption_out_dir)
        treatments = await self.treatment_service.batch_treatment_generate(
            captions, treatment_out_dir
        )
        return treatments
