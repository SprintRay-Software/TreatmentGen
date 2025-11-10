# 口腔全景影像报告生成

## 项目简介

本项目用于将口腔全景影像检测模型输出的结构化结果，自动转换为可读的医疗报告与治疗建议。流程分为两步：首先由 `CaptionService` 将检测框、置信度等信息整理成定位描述。随后 `TreatmentService` 调用大语言模型（本地 `vLLM` 或远程接口）生成符合临床风格的报告文本。项目支持批量处理、异步推理，并提供 Modal Serverless 部署脚本。


## 推理模式说明

- **离线模式**：在 GPU 服务器上加载模型（示例为 `Lingshu-7B`），`TreatmentService.offline_inference` 通过本地 `vLLM` 生成报告。
- **在线模式**：配置 `model_name` 与 `base_url`，调用 `APIClient` 发送到自建或第三方兼容 OpenAI Chat Completions 接口。
- **多阶段提示词**：Draft → Revision → Treatment，提示词模板位于 `app/prompt/`，可按需调整行业术语或评审规则。

## 目录结构

```text
report_generation/
├── app/
│   ├── client.py            # 在线推理 API 客户端封装
│   ├── core/                # 基础配置与日志
│   ├── prompt/              # Draft/Revision/Treatment 提示词模版
│   └── service/             # Caption 与 Treatment 服务实现
├── data/                    # 示例输入
├── main.py                  # 本地批处理入口
├── deploy.py                # Modal 部署脚本
├── usage.py                 # HTTP 推理调用示例
├── tests/                   # 单元测试
├── pyproject.toml           # 依赖与工具配置
└── README.md
```

## 环境准备

- Python 3.12 及以上版本
- 建议使用 `uv` 或 `venv` 隔离环境

安装依赖：

```bash
uv sync
# 或
pip install -e .
```

## 输入数据格式

`CaptionService` 期望的 JSON 结构需包含 `properties` 字段，内部含有以下键：`Teeth`、`Quadrants`、`Missing teeth`、`JawBones`。
```json
{
  "properties": {
    "Teeth": [
      {
        "tooth_id": "11",
        "score": 0.95,
        "conditions": {
          "Caries": {
            "present": true,
            "bbox": [...],
            "score": [0.82]
          }
        }
      }
    ],
    "Quadrants": [...],
    "Missing teeth": [...],
    "JawBones": [...]
  }
}
```

## 输出数据格式

```python
[{'id': '0', 'treatment': ''}]
```

## 本地批处理流程

1. 将结构化检测结果 JSON 放入 `data/`（或修改 `main.py` 中的 `data_dir` 指向自定义目录）。
2. 根据需要调整 `TreatmentService` 的 `model_name`、`base_url` 等参数；若本地已有 vLLM 引擎，可传入 `LLM` 实例。
3. 执行：
   ```bash
   python main.py
   ```
4. 输出：
   - 定位描述：`out_caption/caption_{id}.txt` 与 `caption_{id}.json`
   - 治疗建议：`out_treatment_zh/treatment_{id}.md`

运行过程中日志默认写入 `logs/` 目录，可通过 `app/core/logger.py` 修改日志级别与位置。

## Modal 云端部署

`deploy.py` 提供 Modal Serverless 部署示例：

1. 确保已登录 Modal（`modal setup`）。
2. 根据需求修改脚本中的 `MODEL_NAME`、`MODEL_REVISION`、资源配额等参数。
3. 部署：
   ```bash
   modal deploy deploy.py
   ```

## HTTP 接口示例

`usage.py` 展示了如何将结构化数据直接 POST 到部署好的服务：

```bash
python usage.py
```

运行前需填充 `TOKEN_ID`、`TOKEN_SECRET`、`APP_URL`，并确保输入的 JSON 结构与服务端一致。

