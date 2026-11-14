#!/usr/bin/env python3
"""Optional offline pixel sheet: SVG original beside built TrueType glyph.

For a source checkout it samples a small selection. Requires Pillow + CairoSVG.
"""
import argparse
import io
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import cairosvg

ROOT = Path(__file__).resolve().parent.parent

def main(package: Path, source: Path, output: Path, limit: int):
    m = json.loads((package / 'tool/manifest.json').read_text())['icons']
    cp = json.loads((package / 'tool/codepoints.json').read_text())['assignments']
    names = sorted(set(m['regular']) & set(m['filled']))[:limit]
    sz, pad, rowh = 96, 24, 144
    im = Image.new('RGB', (800, len(names) * rowh + 55), '#ffffff')
    draw = ImageDraw.Draw(im)
    labels = ['SVG Regular', 'TTF Regular', 'SVG Filled', 'TTF Filled']
    for i, label in enumerate(labels):
        draw.text((170 + i*157, 16), label, fill='#222222')
    fonts = {'regular': ImageFont.truetype(package / 'assets/fonts/MingCuteKitRegular.ttf', 96),
             'filled': ImageFont.truetype(package / 'assets/fonts/MingCuteKitFilled.ttf', 96)}
    for row, name in enumerate(names):
        base = 50 + row * rowh
        draw.text((6, base+40), name, fill='#333333')
        for idx, style in enumerate(('regular','filled')):
            ref = m[style][name]
            raw = (source / ref['source']).read_bytes()
            svg_im = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=raw,output_width=96,output_height=96))).convert('RGBA')
            # Transparent SVG glyph -> dark ink on white sheet.
            fg = Image.new('RGBA', (96,96), '#202020')
            fg.putalpha(svg_im.getchannel('A'))
            px = 166 + (idx*2)*157
            im.paste(fg.convert('RGB'), (px,base), fg)
            f = fonts[style]
            text = chr(int(cp[name], 16))
            # Glyph em box: same 0..24 viewBox as SVG, without visually
            # rescaling the glyph to its tight bounds (which would hide errors).
            tile = Image.new('RGBA',(96,96),(0,0,0,0))
            d = ImageDraw.Draw(tile)
            d.text((0, 96*896/1024),text,font=f,fill='#202020',anchor='ls')
            im.paste(tile.convert('RGB'),(px+157,base),tile)
    output.parent.mkdir(parents=True,exist_ok=True)
    im.save(output)
    print(f'Comparison preview: {output}')

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,default=ROOT/'tool/tests/fixtures/upstream')
    p.add_argument('--output',type=Path,default=ROOT/'tool/fixture-preview.png')
    p.add_argument('--limit',type=int,default=8)
    p.add_argument('--package',type=Path,default=ROOT)
    a=p.parse_args()
    main(a.package,a.source,a.output,a.limit)
