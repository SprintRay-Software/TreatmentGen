import os
from collections.abc import Awaitable, Callable
from typing import Any

import modal

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

_services: dict[str, Any] | None = None


def _get_services() -> dict[str, Any]:
    global _services

    if _services is None:
        from langfuse import Langfuse
        from vllm import LLM, SamplingParams

        from app.core.logger import logger
        from app.service.caption_service import CaptionService
        from app.service.treatment_service import TreatmentService

        logger.info(f"初始化 vLLM 引擎: {MODEL_NAME}")

        llm = LLM(
            model=MODEL_NAME,
            revision=MODEL_REVISION,
            max_model_len=MAX_MODEL_LEN,
            tensor_parallel_size=N_GPU,
            enforce_eager=FAST_BOOT,
            gpu_memory_utilization=0.8,
            trust_remote_code=True,
        )

        sampling_params = SamplingParams(
            temperature=0.7,
            top_p=1,
            repetition_penalty=1,
            max_tokens=2048,
            stop_token_ids=[],
        )

        logger.info("vLLM 引擎初始化完成")

        _ = llm.generate(["hi"], SamplingParams(max_tokens=1, temperature=0.0))
        logger.info("vLLM 引擎热身完成")

        treatment_service = TreatmentService(
            llm=llm,
            sampling_params=sampling_params,
        )
        caption_service = CaptionService()

        langfuse = Langfuse(
            public_key=os.getenv("public_key"),
            secret_key=os.getenv("secret_key"),
            base_url=os.getenv("host"),
        )

        if langfuse.auth_check():
            logger.info("Langfuse 认证成功")
        else:
            logger.error("Langfuse 认证失败")

        _services = {
            "treatment_service": treatment_service,
            "caption_service": caption_service,
        }

    return _services


@app.function(
    image=image,
    cpu=CPU,
    memory=MEMORY,
    gpu=f"L40S:{N_GPU}",
    enable_memory_snapshot=snap,
    experimental_options={"enable_gpu_snapshot": snap},
    scaledown_window=3 * MINUTES,
    timeout=10 * MINUTES,
    volumes=volumes,
    secrets=[
        modal.Secret.from_name("langfuse"),
        modal.Secret.from_name("modal-auth"),
    ],
)
@modal.asgi_app()
def fastapi_app():
    from fastapi import FastAPI, Request, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, Response
    from starlette.middleware.base import BaseHTTPMiddleware

    from app.core.logger import logger

    web_app = FastAPI()

    # 配置 CORS 中间件
    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*", "X-Modal-Key", "X-Modal-Secret"],
    )

    VALID_MODAL_KEY = os.getenv("modal_key", "")
    VALID_MODAL_SECRET = os.getenv("modal_secret", "")

    if not VALID_MODAL_KEY or not VALID_MODAL_SECRET:
        import warnings

        warnings.warn(
            "MODAL_KEY or MODAL_SECRET not configured. "
            "Authentication will be disabled. "
            "Please configure these values in Modal Secret 'modal-auth'.",
            stacklevel=2,
        )

    class ModalAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(
            self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ):
            if request.method == "OPTIONS":
                return await call_next(request)

            if not VALID_MODAL_KEY or not VALID_MODAL_SECRET:
                return await call_next(request)

            modal_key = request.headers.get("X-Modal-Key", "")
            modal_secret = request.headers.get("X-Modal-Secret", "")
            logger.info(request.headers)

            if not modal_key or not modal_secret:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Modal-Key and Modal-Secret headers are required."},
                )

            if modal_key != VALID_MODAL_KEY or modal_secret != VALID_MODAL_SECRET:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid Modal-Key or Modal-Secret. Authentication failed."},
                )

            return await call_next(request)

    web_app.add_middleware(ModalAuthMiddleware)

    @web_app.options("/health")
    async def preflight_health():
        return Response(status_code=200)

    @web_app.options("/generate")
    async def preflight_generate():
        return Response(status_code=200)

    @web_app.get("/health")
    async def health() -> dict[str, Any]:
        _get_services()
        return {"status": 200}

    @web_app.post("/generate")
    async def generate(request: Request) -> list[dict[str, Any]]:
        payload: dict[str, Any] | list[dict[str, Any]] = await request.json()

        services = _get_services()
        treatment_service = services["treatment_service"]
        caption_service = services["caption_service"]

        captions = caption_service.batch_caption_generate(payload, CAPTION_OUTPUT_DIR)
        treatments = await treatment_service.batch_treatment_generate(
            captions, TREATMENT_OUTPUT_DIR
        )

        return treatments

    return web_app
