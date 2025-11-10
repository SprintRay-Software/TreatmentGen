import asyncio
import json

from app.service.caption_service import CaptionService
from app.service.treatment_service import TreatmentService


async def main():
    caption_service = CaptionService()
    treatment_service = TreatmentService(
        model_name="Lingshu-7B",
        base_url="http://192.168.112.180:8000",
    )

    import os
    import re

    data_dir = "./data"
    data = []
    file_ids = []
    for filename in sorted(os.listdir(data_dir)):
        filepath = os.path.join(data_dir, filename)
        if os.path.isfile(filepath) and filename.endswith(".json"):
            match = re.search(r"(\d+)\.json$", filename)
            if match:
                file_id = match.group(1)
            else:
                file_id = filename.replace(".json", "")

            with open(filepath, encoding="utf-8") as fp:
                file_data = json.load(fp)
                data.append(file_data)
                file_ids.append(file_id)

    caption = caption_service.batch_caption_generate(
        data, caption_out_dir="./out_caption", file_ids=file_ids
    )
    _ = await treatment_service.batch_treatment_generate(
        captions=caption,
        treatment_out_dir="./out_treatment_en",
    )


if __name__ == "__main__":
    asyncio.run(main())
