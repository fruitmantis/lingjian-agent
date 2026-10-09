"""Fixed ten-chapter partner report; no migration or general editing framework."""
import re
from dataclasses import dataclass
from pathlib import Path

CHAPTERS = (
    '公司概况', '公司规模与收入情况', '与头部科技企业（华为/阿里/字节）合作情况',
    '华为认证与资质情况', 'AI技术能力与解决方案', '重点行业案例',
    '负向事件与合规风险排查', '适合开展合作的领域建议', '合作注意事项', '数据来源',
)
MISSING = '现有资料未提供'
_NUMBERS = dict(zip('一二三四五六七八九', range(1, 10)), 十=10)
_TABLE_HEADERS = {1: ('项目', '信息'), 4: ('类别', '认证/资质名称', '级别与说明'), 6: ('时间', '项目/业务', '客户', '金额', '行业')}

class ReportError(ValueError):
    pass


def heading(number):
    return f'## {number}. {CHAPTERS[number-1]}'


def chapter_number(line):
    line = re.sub(r'^#{1,2}\s+', '', line.strip())
    match = re.fullmatch(r'(?:第)?([一二三四五六七八九十]|10|[1-9])(?:章\s*|[、.．]\s*)(.+)', line)
    if not match:
        return None
    token, title = match.groups(); number = _NUMBERS.get(token) or int(token)
    clean = lambda value: re.sub(r'[\s（）()/／]', '', value).lower().replace('专题', '')
    title = clean(title)
    accepted = {clean(CHAPTERS[number-1])}
    if number == 4: accepted.add(clean('华为认证与资质核查'))
    if number == 10: accepted.add(clean('数据来源与免责声明'))  # Read existing Word/legacy headings.
    return number if title in accepted else None


@dataclass
class Report:
    prefix: str
    chapters: list[str]

    @property
    def text(self):
        return self.prefix + ''.join(self.chapters)


def parse(text):
    """Keep exact slices so unmodified chapters, including whitespace, survive."""
    matches = []; offset = 0
    for line in text.splitlines(keepends=True):
        number = chapter_number(line)
        if number: matches.append((number, offset, offset+len(line)))
        offset += len(line)
    candidates = []
    for i, (number, start, _) in enumerate(matches):
        group = matches[i:i+10]
        if number != 1 or [h[0] for h in group] != list(range(1, 11)): continue
        ends = [h[1] for h in group[1:]] + [matches[i+10][1] if len(matches)>i+10 else len(text)]
        # A table of contents has no chapter body. Never accept it as the report.
        if any(not text[h[2]:end].strip() for h,end in zip(group,ends)): continue
        candidates.append(Report(text[:start], [text[h[1]:end] for h,end in zip(group,ends)]))
    if len(candidates) != 1 or candidates[0].text != text:
        raise ReportError('无法可靠识别完整十章正文，请检查报告标题与目录；原画像保持不变。')
    return candidates[0]


def table_markdown(rows):
    width = max(map(len, rows))
    def cell(value):
        return value.replace('\\', '\\\\').replace('|', '\\|').replace('\n', '<br>')
    lines = ['| ' + ' | '.join(cell(v) for v in row + ['']*(width-len(row))) + ' |' for row in rows]
    return '\n'.join([lines[0], '| ' + ' | '.join(['---']*width) + ' |', *lines[1:]])


def empty_report():
    sections = []
    for number in range(1,11):
        body = MISSING
        sections.append(heading(number)+'\n\n'+body+'\n\n')
    return Report('',sections)


def from_docx(path):
    """Format native paragraphs/tables only. The original and extracted_text stay intact."""
    from docx import Document
    from docx.text.paragraph import Paragraph
    from docx.table import Table
    blocks = []
    for block in Document(str(path)).iter_inner_content():
        if isinstance(block, Paragraph):
            text = block.text
            number = chapter_number(text)
            style = getattr(block.style, 'name', '') or ''
            if number: blocks.append(heading(number))
            elif re.sub(r'\s','',text) == '目录': blocks.append('目录')
            elif style.startswith('Heading') and text.strip(): blocks.append('### '+text)
            else: blocks.append(text)
        elif isinstance(block, Table):
            rows=[]
            for row in block.rows:
                cells=[]; seen=set()
                for cell in row.cells:
                    if cell._tc in seen: cells.append('')
                    else: cells.append(cell.text); seen.add(cell._tc)
                rows.append(cells)
            blocks.append(table_markdown(rows))
    report = parse('\n\n'.join(blocks).strip()+'\n\n')
    # Cover name/date/qualifiers stay; TOC entries do not become report text.
    report.prefix = re.split(r'(?m)^目\s*录\s*$',report.prefix,maxsplit=1)[0].rstrip()+'\n\n' if re.search(r'(?m)^目\s*录\s*$',report.prefix) else report.prefix
    for number in _TABLE_HEADERS: validate_body(number, report.chapters[number-1].split('\n',1)[1])
    return report


def baseline(current, originals):
    if originals:
        latest = max(originals,key=lambda d:(d['created_at'],d['id']))
        path=Path(latest['file_path'])
        if not path.is_file(): raise ReportError('原 Word 文件不可用，无法恢复十章底稿；原画像保持不变。')
        return from_docx(path), False
    if current and current.strip():
        raise ReportError('当前画像不是完整十章报告，且没有可恢复的原 Word；请重新导入，原画像保持不变。')
    return empty_report(), True


def validate_body(number, body):
    if not body.strip() or body.lstrip().startswith(('{','[','```')):
        raise ReportError('章节内容为空或格式不合法，未覆盖原画像。')
    if any(chapter_number(line) or re.match(r'^#{1,2}\s',line) for line in body.splitlines()):
        raise ReportError('章节内容包含其他一级章节，未覆盖原画像。')
