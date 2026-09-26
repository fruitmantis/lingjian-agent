"""Native text only: no OCR, image extraction, external requests or silent truncation."""
from pathlib import Path
import re
import bleach
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from .material_contract import file_type as get_file_type

TEXT_TAGS = ['p','div','span','br','h1','h2','h3','h4','h5','h6','ul','ol','li','blockquote','pre','code','table','thead','tbody','tfoot','tr','th','td','strong','b','em','i','hr','a']
REMOVE_TAGS = ['script','style','img','picture','svg','canvas','iframe','object','embed','video','audio','source','link','meta','form','input','button','textarea','noscript','template']


def decode_text(data: bytes) -> str:
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = data.decode('utf-16')
    else:
        if b'\x00' in data: raise ValueError('文件不是可读取的文本')
        try: text = data.decode('utf-8-sig')
        except UnicodeDecodeError: text = data.decode('gb18030')
    if any(ord(c) < 32 and c not in '\n\r\t\f' for c in text):
        raise ValueError('文件包含二进制控制字符')
    return text


def clean_html(raw: str) -> str:
    soup = BeautifulSoup(raw, 'html.parser')
    for node in soup.find_all(REMOVE_TAGS): node.decompose()
    # Attributes (including images, styles, event handlers, URLs and forms) never survive.
    return bleach.clean(str(soup.body or soup), tags=TEXT_TAGS, attributes={}, protocols=[], strip=True, strip_comments=True)


def markdown_html(raw: str) -> str:
    parser = MarkdownIt('commonmark', {'html': True}).enable('table')
    tokens = parser.parse(raw)
    def remove_images(items):
        for token in items:
            if token.type == 'image':
                token.type = 'text'; token.content = ''; token.children = None
            elif token.children: remove_images(token.children)
    remove_images(tokens)
    return clean_html(parser.renderer.render(tokens, parser.options, {}))


def html_text(raw: str) -> str:
    soup = BeautifulSoup(raw, 'html.parser')
    # Preserve headings, list/table boundaries and code text without image alt/URLs.
    for br in soup.find_all('br'): br.replace_with('\n')
    for cell in soup.find_all(['td','th']): cell.append('\t')
    for item in soup.find_all(['p','div','h1','h2','h3','h4','h5','h6','li','tr','pre','blockquote']): item.append('\n')
    return re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', soup.get_text()).strip()


def extract_text(file_path: str, file_type: str) -> str:
    p = Path(file_path)
    if file_type == 'pdf':
        from PyPDF2 import PdfReader
        reader = PdfReader(str(p), strict=False)
        if reader.is_encrypted and not reader.decrypt(''): raise ValueError('PDF 已加密，无法提取文字')
        return '\n\n'.join(filter(None, (page.extract_text() for page in reader.pages))).strip()
    if file_type == 'docx':
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        doc = Document(str(p))
        def blocks(parent):
            result = []
            for block in parent.iter_inner_content():
                if isinstance(block, Paragraph): result.append(block.text)
                elif isinstance(block, Table):
                    for row in block.rows:
                        seen=set(); values=[]
                        for cell in row.cells:
                            if cell._tc in seen: continue
                            seen.add(cell._tc); values.append('\n'.join(blocks(cell)))
                        result.append('\t'.join(values))
            return result
        return '\n'.join(blocks(doc)).strip()
    if file_type == 'pptx':
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        def shapes_text(shapes):
            for shape in shapes:
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP: yield from shapes_text(shape.shapes)
                elif shape.has_text_frame: yield shape.text
                elif shape.has_table:
                    for row in shape.table.rows:
                        yield '\t'.join(cell.text for cell in row.cells if not cell.is_spanned)
        pages=[]
        for i,slide in enumerate(Presentation(str(p)).slides, 1):
            content='\n'.join(t for t in shapes_text(slide.shapes) if t.strip())
            if content: pages.append(f'第 {i} 页\n{content}')
        return '\n\n'.join(pages)
    raw=decode_text(p.read_bytes())
    if file_type == 'txt': return raw.strip()
    if file_type == 'markdown': return html_text(markdown_html(raw))
    if file_type == 'html': return html_text(clean_html(raw))
    raise ValueError('不支持此文件类型')
