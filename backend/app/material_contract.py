"""One document allow-list and the user-approved case taxonomy, shared with the UI."""
import json
from pathlib import Path
from fastapi import HTTPException

CONTRACT = json.loads((Path(__file__).resolve().parents[2] / 'shared/partner-materials.json').read_text())
EXTENSIONS = {ext: row['type'] for row in CONTRACT['formats'] for ext in row['extensions']}
CATEGORIES = {child['id']: (group['name'], child['name']) for group in CONTRACT['categories'] for child in group['children']}


def file_type(filename):
    return EXTENSIONS.get(Path(filename).suffix.lower(), '')


def check_category(value):
    if value not in CATEGORIES:
        raise HTTPException(422, '请选择有效的案例两级分类')
    return value


def category_names(value):
    first, second = CATEGORIES.get(value, ('待分类', '待分类'))
    return {'category_group': first, 'category_name': second}
