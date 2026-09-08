"""One shared dictionary; legacy ambiguity is preserved, never inferred as a standard."""
import json
import re
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

STANDARD = json.loads((Path(__file__).resolve().parents[2] / 'shared/business-taxonomy.json').read_text())
INDUSTRIES = STANDARD['industries']
REGION_TYPES = STANDARD['region_types']
REGIONS = [x for group in REGION_TYPES.values() for x in group]

def tokens(value):
    if value is None or value == '': return []
    if isinstance(value, str): values = re.split(r'[,，、;/；|\n]+', value)
    elif isinstance(value, list) and all(isinstance(x, str) for x in value): values = value
    else: raise ValueError('行业/区域必须为标准值列表或逗号分隔文本')
    return list(dict.fromkeys(x.strip() for x in values if x.strip()))

def classify(value, kind):
    allowed = INDUSTRIES if kind == 'industry' else REGIONS
    known, pending = [], []
    for raw in tokens(value):
        if raw in ('未识别','未知','暂无','未提供'): continue
        target = STANDARD['aliases'][kind].get(raw, raw)
        dest = known if target in allowed else pending
        item = target if target in allowed else raw
        if item not in dest: dest.append(item)
    return known, pending

def canonical(value, kind):
    return ','.join(classify(value, kind)[0])

def validate_standard(value, kind):
    if value is None: return None
    allowed = INDUSTRIES if kind == 'industry' else REGIONS
    values = tokens(value)
    if any(x not in allowed for x in values):
        raise ValueError('请使用正式行业或省级/海外标准区域，不接受城市或未确认分类')
    return ','.join(values)

def preserve_pending(previous, current, kind):
    return ','.join(tokens(current) + classify(previous, kind)[1])

def region_groups(value):
    selected = classify(value, 'region')[0]
    return [{'region_type': kind, 'regions': [x for x in selected if x in values]}
            for kind, values in REGION_TYPES.items() if any(x in values for x in selected)]

def project_partner(value):
    result = dict(value)
    result['classification_pending'] = {'industries':classify(result.get('industries'),'industry')[1],
                                        'regions':classify(result.get('service_areas'),'region')[1]}
    result['industries'] = canonical(result.get('industries'),'industry')
    result['service_areas'] = canonical(result.get('service_areas'),'region')
    result['region_groups'] = region_groups(result['service_areas'])
    return result

class RegionGroup(BaseModel):
    region_type: Literal['domestic','overseas']
    regions: list[str]
    @model_validator(mode='after')
    def check_group(self):
        if any(x not in REGION_TYPES[self.region_type] for x in self.regions):
            raise ValueError('区域不属于所选国内/海外分组')
        self.regions = list(dict.fromkeys(self.regions))
        return self

class ClassificationInput(BaseModel):
    industries: str | None = None
    service_areas: str | None = None
    region_groups: list[RegionGroup] | None = None
    @field_validator('industries',mode='before')
    @classmethod
    def industry_values(cls,value): return validate_standard(value,'industry')
    @field_validator('service_areas',mode='before')
    @classmethod
    def region_values(cls,value): return validate_standard(value,'region')
    @model_validator(mode='after')
    def groups_to_legacy_storage(self):
        if self.region_groups is not None:
            combined = ','.join(dict.fromkeys(x for g in self.region_groups for x in g.regions))
            if self.service_areas is not None and set(tokens(self.service_areas)) != set(tokens(combined)):
                raise ValueError('regions 与 service_areas 不一致')
            self.service_areas = combined
        return self

class ClassificationOutput(BaseModel):
    classification_pending: dict[str,list[str]] = Field(default_factory=dict)
    region_groups: list[RegionGroup] = Field(default_factory=list)
    @model_validator(mode='before')
    @classmethod
    def project(cls,value):
        if not isinstance(value, dict): return value
        result = project_partner(value)
        # Keep pending information if an already projected value is serialized again.
        if 'classification_pending' in value: result['classification_pending'] = value['classification_pending']
        return result

def taxonomy_prompt():
    return ('结构化行业只能从'+json.dumps(INDUSTRIES,ensure_ascii=False)+'选择，可多选。'
            '结构化区域按region_type分为domestic和overseas，各组regions可多选：'
            +json.dumps(REGION_TYPES,ensure_ascii=False)+
            '。国内只到省级，海外只使用六个区域。允许同时覆盖两组。'
            '不得把城市、国家、宏观大区或行业子类作为标准值；无法确定时留空，不猜。'
            '只约束结构化字段，自然语言原文保留。现有文本型字段使用逗号分隔标准值。')
