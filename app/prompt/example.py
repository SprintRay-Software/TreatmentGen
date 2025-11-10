INPUT_EXAMPLE = """
This localization caption provides multi-dimensional spatial analysis of anatomical structures and pathological findings for this panoramic dental x-ray image, including:

Teeth visibility with center points (total: 26):
[
{'point_2d': [1290, 550], 'tooth_id': '21', 'score': 0.9},
{'point_2d': [1272, 812], 'tooth_id': '31', 'score': 0.89},
...
]
Wisdom teeth detection (total: 3):
[
{'box_2d': [672, 332, 787, 561], 'tooth_id': '18', 'is_impacted': false, 'score': 0.65},
{'box_2d': [1680, 565, 1883, 731], 'tooth_id': '38', 'is_impacted': false, 'score': 0.59},
...
]
Dental caries detection (total: 2):
[
{'box_2d': [1695, 615, 1767, 679], 'tooth_id': '38', 'label': 'Caries', 'score': 0.56},
{'box_2d': [1667, 556, 1912, 759], 'tooth_id': '38', 'label': 'Deep caries', 'score': 0.46}
]
Periapical lesions detection (total: 1):
[
{'box_2d': [1473, 854, 1521, 901], 'tooth_id': '35', 'label': 'Periapical lesions (Granuloma)', 'score': 0.84}
]
Historical treatments (total: 9):
[
{'box_2d': [1732, 578, 1771, 615], 'tooth_id': '38', 'label': 'Filling', 'score': 0.81},
...
]
Mandibular canal visibility (total: 2):
[
{'box_2d': [1601, 531, 2066, 1062], 'label': 'Mandibular canal', 'score': 0.94},
{'box_2d': [443, 413, 855, 975], 'label': 'Mandibular canal', 'score': 0.9}
]
Maxillary sinussis visibility (total: 2):
[
{'box_2d': [1380, 16, 1801, 317], 'label': 'Maxillary sinus', 'score': 0.81},
{'box_2d': [699, 15, 1084, 302], 'label': 'Maxillary sinus', 'score': 0.82}
]
"""

OUTPUT_EXAMPLE = """
This is a panoramic dental X-ray image, which provides a broad view of the entire mouth, including the teeth, jawbones, sinuses, and other structures. Below is a detailed analysis of the image:

**Teeth-Specific Observations**
1.  **General Condition:**
    - 26 teeth visualized with findings suggestive of clear anatomical definition
    - 3 wisdom teeth detected:
        - #18: Erupted (suspected, recommend clinical review)
        - #28: Erupted (suspected, recommend clinical review)
        - #38: Erupted (suspected, recommend clinical review)
2.  **Pathological Findings:**
    - #18: sign of caries
    - #38: Suspected deep caries
    - #35: Imaging features sign of periapical granuloma
3.  **Historical Interventions:**
    - #15,16,23,24,25,38: sign of fillings
    - #36: Imaging features sign of dental implant with crown restoration
    - #25: signs of root canal treatment with post-core restoration

**Jaw-Specific Observations**
1.  **Bone Architecture:**
    - No apparent bone loss in the image
2.  **Visible Structures:**
    - Imaging features signs of bilateral mandibular canals

**Clinical Summary & Recommendations**
1.  **Priority Concerns:**
    - Periapical lesion at #35 requires endodontic evaluation
    - Deep caries in #38 needs immediate intervention
2.  **Preventive Measures:**
    - Monitor suspected caries at #18 with radiographic follow-up
3.  **Follow-up Protocol:**
    - 6-month recall for caries monitoring (particularly suspected areas)
    - Bitewing series recommended for interproximal caries detection

Further clinical correlation with physical examination and patient history is recommended for a comprehensive diagnosis.
"""
