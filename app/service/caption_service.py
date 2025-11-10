import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.core.logger import logger


class CaptionService:
    def load_data(self) -> list[dict[str, list[dict[str, Any]]]] | None:
        if not self.input_dir_or_file:
            logger.error("Please select input directory or file")
            return None

        def load_single_file(input_path: str) -> dict[str, Any]:
            with open(input_path, encoding="utf-8") as fp:
                data = json.load(fp)
            return {
                "Teeth": data["properties"]["Teeth"],
                "Quadrants": data["properties"]["Quadrants"],
                "Missing teeth": data["properties"]["Missing teeth"],
                "JawBones": data["properties"]["JawBones"],
            }

        if self.input_dir_or_file and os.path.isdir(self.input_dir_or_file):
            input_list = [
                os.path.join(self.input_dir_or_file, name)
                for name in sorted(os.listdir(self.input_dir_or_file))
                if name.endswith(".json")
            ]
        else:
            input_list = [self.input_dir_or_file]

        batch_data = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(load_single_file, input_path)
                for input_path in input_list
            ]
            batch_data = [future.result() for future in futures]

        return batch_data

    @staticmethod
    def groups_from_struct(
        data: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        def get_info(jawbones_data: dict[str, Any], label: str) -> list[dict[str, Any]]:
            info = jawbones_data.get("conditions", {}).get(label, {})
            if not info:
                return []

            info_bbox, info_score = info.get("bbox", []), info.get("score", 0.0)
            return [
                {
                    "bbox": bbox,
                    "label": label,
                    "score": score,
                }
                for bbox, score in zip(info_bbox, info_score, strict=False)
            ]

        teeth_info, wise_teeth_info, caries_info, treatment_info, periapical_info = (
            [],
            [],
            [],
            [],
            [],
        )

        for tooth in data.get("Teeth", []):
            if tooth.get("is_wisdom_tooth", False):
                conditions = tooth.get("conditions", {})
                is_impacted = conditions.get("Impacted tooth", {}).get("present", False)
                is_impacted_score = conditions.get("Impacted tooth", {}).get(
                    "score", 0.0
                )
                wise_teeth_info.append(
                    {
                        "tooth_id": tooth.get("tooth_id", ""),
                        "is_impacted": is_impacted,
                        "bbox": tooth.get("bbox", []),
                        "tooth_score": tooth.get("score", 0.0),
                        "impacted_score": is_impacted_score,
                    }
                )

            teeth_fields = ["tooth_id", "score", "center"]
            teeth_info.append({k: tooth.get(k, "") for k in teeth_fields})

        # Get all teeth with conditions for convenience
        teeth_w_conditions = [
            tooth for tooth in data.get("Teeth", []) if tooth.get("conditions", {})
        ]
        for tooth in teeth_w_conditions:
            conditions = tooth.get("conditions", {})
            caries_fields = ["Deep caries", "Caries"]
            for label in caries_fields:
                if conditions.get(label, {}).get("present", False):
                    caries_info.append(
                        {
                            "tooth_id": tooth.get("tooth_id", ""),
                            "bbox": conditions.get(label, {}).get("bbox", []),
                            "score": conditions.get(label, {}).get("score", 0.0),
                            "label": label,
                        }
                    )

            treatment_fields = [
                "Filling",
                "Root canal treatment",
                "Root piece",
                "Impacted tooth",
                "Crown",
            ]
            for label in treatment_fields:
                if conditions.get(label, {}).get("present", False):
                    treatment_info.append(
                        {
                            "tooth_id": tooth.get("tooth_id", ""),
                            "bbox": conditions.get(label, {}).get("bbox", []),
                            "score": conditions.get(label, {}).get("score", 0.0),
                            "label": label,
                        }
                    )

            # TODO - If periapical lesion occur in multiple teeth, then combine them into one, like "tooth_id": "14, 36"
            periapical_fields = ["Periapical lesion", "Periapical lesions"]
            for label in periapical_fields:
                if conditions.get(label, {}).get("present", False):
                    periapical_info.append(
                        {
                            "tooth_id": tooth.get("tooth_id", ""),
                            "bbox": conditions.get(label, {}).get("bbox", []),
                            "score": conditions.get(label, {}).get("score", 0.0),
                            "label": "Periapical lesion (Cyst)",
                            "type": conditions.get(label, {}).get("type", ""),
                        }
                    )

        jawbones_data = data.get("JawBones", [])[0] if data.get("JawBones", []) else {}
        canal_info, sinuses_info = (
            get_info(jawbones_data, "Mandibular canal"),
            get_info(jawbones_data, "Maxillary sinus"),
        )

        return {
            "Teeth visibility with center points": teeth_info,
            "Wisdom teeth detection": wise_teeth_info,
            "Dental caries detection": caries_info,
            "Periapical lesion detection": periapical_info,
            "Historical treatments": treatment_info,
            "Mandibular canal visibility": canal_info,
            "Maxillary sinuses visibility": sinuses_info,
        }

    @staticmethod
    def render_caption(
        groups_data: dict[str, list[dict[str, Any]]],
        rule_notes: list[str] | None = None,
    ) -> str:
        lines = []
        lines.append(
            "This localization caption provides multi-dimensional spatial analysis of anatomical structures and pathological findings for this panoramic dental X-ray image, including:\n"
        )
        for title, items in groups_data.items():
            lines.append(f"{title} (total: {len(items)}):" + "\n[")
            for it in items:
                lines.append("  " + json.dumps(it, ensure_ascii=False))
            lines.append("]")
        if rule_notes:
            lines.append("Knowledge-based notes:")
            for n in rule_notes:
                lines.append(f"  - {n}")
            lines.append("")
        return "\n".join(lines)

    def batch_caption_generate(
        self,
        batch_data: list[dict[str, Any]] | dict[str, Any],
        caption_out_dir: str,
        file_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if isinstance(batch_data, dict):
            batch_data = [batch_data.get("properties", batch_data)]
        else:
            batch_data = [item.get("properties", item) for item in batch_data]

        groups_data = [self.groups_from_struct(data) for data in batch_data]

        captions = []
        os.makedirs(caption_out_dir, exist_ok=True)
        for idx, groups in enumerate(groups_data):
            caption = self.render_caption(groups)
            idx = file_ids[idx] if file_ids and idx < len(file_ids) else str(idx)
            with open(
                os.path.join(caption_out_dir, f"caption_{idx}.txt"),
                "w",
                encoding="utf-8",
            ) as fp:
                fp.write(caption)
            with open(
                os.path.join(caption_out_dir, f"caption_{idx}.json"),
                "w",
                encoding="utf-8",
            ) as fp:
                json.dump(groups, fp, ensure_ascii=False, indent=2)
            captions.append(
                {
                    "id": idx,
                    "caption": caption,
                }
            )

        return captions
