# SPDX-License-Identifier: GPL-3.0-only
"""Build six illustrated guides from reviewed text and real demonstration captures.
Authoring requirements: ReportLab and Pillow. No runtime dependencies are added.
"""
import io
import json
from pathlib import Path
import re
import sys
from xml.sax.saxutils import escape
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.tableofcontents import TableOfContents
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from app_version import VERSION,DISPLAY_VERSION
from i18n import LANGUAGES
BLUE=colors.HexColor('#1765c1')
INK=colors.HexColor('#172b45')
MUTED=colors.HexColor('#58677b')
PAGE_WIDTH,PAGE_HEIGHT=A4
MARGIN=42
CONTENT_WIDTH=PAGE_WIDTH-2*MARGIN-12
ASSETS=ROOT/'docs/manuals'
BOOK=json.loads((ASSETS/'guidebook.json').read_text(encoding='utf-8'))
META=json.loads((ASSETS/'guide_meta.json').read_text(encoding='utf-8'))
PICTURES={4:'files',5:'editor',6:'transport',7:'route',8:'progress',9:'proposal',10:'context',14:'connection',18:'time',20:'stats',21:'waypoint'}
FOCUS={'files':(.025,.19,.975,.945),'editor':(.025,.19,.975,.945),'stats':(.025,.19,.975,.945),
       'transport':(.025,.19,.34,.945),'route':(.025,.19,.34,.945),'time':(.025,.19,.34,.945),
       'progress':(.02,.129,.98,.188)}

class Screenshot(Flowable):
    """Enlarge details by clipping; never alter labels or invent program UI."""
    def __init__(self,path,focus=None,max_width=CONTENT_WIDTH,max_height=630):
        super().__init__()
        with Image.open(path) as image:
            self.pixels=image.size
            data=io.BytesIO()
            image.convert('RGB').save(data,'JPEG',quality=93,subsampling=0,optimize=True)
        data.seek(0)
        self.reader=ImageReader(data)
        self.focus=focus or (0,0,1,1)
        x,y,right,bottom=self.focus
        width,height=self.pixels
        self.scale=min(max_width/(width*(right-x)),max_height/(height*(bottom-y)))
        self.width=width*(right-x)*self.scale
        self.height=height*(bottom-y)*self.scale
        self.hAlign='CENTER'
    def draw(self):
        c=self.canv
        c.saveState()
        clip=c.beginPath()
        clip.rect(0,0,self.width,self.height)
        c.clipPath(clip,stroke=0)
        x,y,right,bottom=self.focus
        width,height=self.pixels
        c.drawImage(self.reader,-x*width*self.scale,-(1-bottom)*height*self.scale,width=width*self.scale,height=height*self.scale)
        c.restoreState()

class GuideDoc(SimpleDocTemplate):
    def afterFlowable(self,flowable):
        if getattr(flowable,'chapter_key',None):
            key=flowable.chapter_key
            title=flowable.getPlainText()
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title,key,level=0)
            self.notify('TOCEntry',(0,title,self.page,key))

def build():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('fonts',nargs='?',default='C:/Windows/Fonts')
    parser.add_argument('--language',choices=list(LANGUAGES))
    options=parser.parse_args()
    fonts=Path(options.fonts)
    pdfmetrics.registerFont(TTFont('Guide',str(fonts/'segoeui.ttf')))
    pdfmetrics.registerFont(TTFont('GuideBold',str(fonts/'segoeuib.ttf')))
    pdfmetrics.registerFontFamily('Guide',normal='Guide',bold='GuideBold')
    styles={
      'cover':ParagraphStyle('cover',fontName='GuideBold',fontSize=31,leading=38,textColor=INK,spaceAfter=18),
      'title':ParagraphStyle('chapter',fontName='GuideBold',fontSize=23,leading=29,textColor=INK,spaceAfter=22),
      'figure':ParagraphStyle('figure',fontName='GuideBold',fontSize=16,leading=20,textColor=INK,spaceAfter=8),
      'front':ParagraphStyle('front',fontName='Guide',fontSize=12,leading=17,textColor=INK,spaceAfter=10),
      'body':ParagraphStyle('body',fontName='Guide',fontSize=12,leading=17.5,textColor=INK,spaceAfter=8),
      'tip':ParagraphStyle('tip',fontName='Guide',fontSize=11,leading=16,textColor=INK,backColor=colors.HexColor('#eef4fc'),borderPadding=10,spaceBefore=16,spaceAfter=10),
      'caption':ParagraphStyle('caption',fontName='Guide',fontSize=10,leading=14,textColor=MUTED,spaceBefore=8),
    }
    out=ROOT/'Handleidingen'
    out.mkdir(exist_ok=True)
    for code in ([options.language] if options.language else LANGUAGES):
        meta=META[code]
        catalogue={} if code=='nl' else json.loads((ROOT/f'src/locales/{code}.json').read_text(encoding='utf-8'))
        localized_version=catalogue.get(DISPLAY_VERSION,DISPLAY_VERSION)
        def rich(text):
            text=text.replace('\u2013','-').replace('\u2014','-')
            pieces=re.split(r'(\[\[.*?\]\])',text)
            return ''.join('<b><font color="#1765c1">'+escape(catalogue.get(p[2:-2],p[2:-2]))+'</font></b>' if p.startswith('[[') else escape(p) for p in pieces)
        def para(text,style='body'):
            return Paragraph(rich(text),styles[style])
        def footer(canvas,doc):
            canvas.saveState()
            canvas.setFont('Guide',9)
            canvas.setFillColor(MUTED)
            canvas.drawString(MARGIN,22,f'RouteRefit {localized_version} | {LANGUAGES[code]} | © 2026 Marco Delnoij | GPL-3.0-only')
            canvas.drawRightString(PAGE_WIDTH-MARGIN,22,str(doc.page))
            canvas.restoreState()
        flow=[Spacer(1,15),para(f'RouteRefit {localized_version}','cover'),para(meta['title'],'cover'),
              para(meta['intro'],'front'),para(meta['mouse'],'front'),para(meta['quick'],'front'),para(meta['zoom'],'front'),para(meta['demo'],'tip'),
              PageBreak(),para(meta['contents'],'title')]
        toc=TableOfContents()
        toc.levelStyles=[ParagraphStyle('toc',fontName='Guide',fontSize=11,leading=15,textColor=INK,spaceBefore=1,leftIndent=0)]
        flow.extend([toc,PageBreak()])
        for number,chapter in enumerate(BOOK[code]):
            if number:flow.append(PageBreak())
            title=para(f"{chapter['id']:02d}. {chapter['title']}",'title')
            title.chapter_key=f"chapter-{chapter['id']:02d}"
            flow.append(title)
            for index,text in enumerate(chapter['steps'],1):
                row=Table([[Paragraph(f'<b>{index}</b>',styles['body']),para(text)]],colWidths=[28,CONTENT_WIDTH-28],hAlign='LEFT')
                row.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('TEXTCOLOR',(0,0),(0,0),BLUE),('LEFTPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
                flow.append(row)
            flow.append(para(meta['note']+' '+chapter['tip'],'tip'))
            name=PICTURES.get(chapter['id'])
            if name:
                path=ASSETS/'screens/0.5.5'/code/(name+'.jpg')
                if not path.is_file():raise ValueError('Missing reviewed screenshot: '+str(path))
                flow.extend([PageBreak(),para(chapter['title'],'figure'),Screenshot(path,FOCUS.get(name)),para(meta['caption'],'caption')])
        filename=out/f'RouteRefit-{VERSION}-handleiding-{code.upper()}.pdf'
        doc=GuideDoc(str(filename),pagesize=A4,leftMargin=MARGIN,rightMargin=MARGIN,topMargin=36,bottomMargin=42,title=f'RouteRefit {localized_version} - {meta["title"]}',author='Marco Delnoij')
        doc.multiBuild(flow,onFirstPage=footer,onLaterPages=footer)
        print(filename.name)

if __name__=='__main__':build()
