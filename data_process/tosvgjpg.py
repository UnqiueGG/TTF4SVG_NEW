#!/usr/bin/env python3
"""
font2svg_batch_rounded_spaces.py
按 stokes.json 顺序导出 fonts/ 下所有 TTF/OTF/TTC 字体的字符为 SVG/JPG
- 动态 viewBox 自动适配字形边界
- SVG path 数据四舍五入为整数
- 命令字母与数字之间保证空格
"""

import os
import json
import argparse
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.recordingPen import RecordingPen
from PIL import Image, ImageDraw, ImageFont
import unicodedata
import re
from tqdm import tqdm

FONTS_DIR = "./fonts"
stokes_FILE = "./stokes.json"

def safe_name_for_file(char, cp):
    """
    根据字符生成文件安全名称：
    - 对非法文件名字符和控制字符使用 Unicode 编码
    - 保证空格和不可打印字符不会出错
    """
    bad_chars = r'[/\\:*?"<>|]'
    if re.search(bad_chars, char):
        return f"U+{cp:04X}"
    cat = unicodedata.category(char)
    if cat.startswith("C") or char.isspace():
        return f"U+{cp:04X}"
    return char

def get_glyph_bounds(font: TTFont, glyph_name):
    """
    获取字形边界框 (xmin, ymin, xmax, ymax)
    - 使用字形自身 boundingBox 或 bounds
    - 若没有提供，使用 RecordingPen 手动计算
    - 防止空字形返回 0,0,0,0
    """
    glyph_set = font.getGlyphSet()
    g = glyph_set[glyph_name]
    if hasattr(g, "boundingBox"):
        return g.boundingBox()
    elif hasattr(g, "bounds") and g.bounds is not None:
        return g.bounds
    else:
        pen = RecordingPen()
        g.draw(pen)
        xs, ys = [], []
        for cmd, pts in pen.value:
            for p in pts:
                xs.append(p[0])
                ys.append(p[1])
        if not xs or not ys:
            return 0,0,0,0
        return min(xs), min(ys), max(xs), max(ys)

def round_path_data(d_attr: str) -> str:
    """
    将 SVG path 数据中的数值四舍五入为整数
    - 避免过多小数导致文件过大
    """
    def repl(m):
        return str(int(round(float(m.group(0)))))
    return re.sub(r"-?\d+\.?\d*(?:e[-+]?\d+)?", repl, d_attr)

def add_space_around_commands(d_attr: str) -> str:
    """
    对 SVG path 的命令字母（M,L,H,V,C,S,Q,T,A,Z，大小写）：
    1. 命令字母前如果紧跟数字，加空格
    2. 命令字母后如果紧跟数字，加空格
    3. 合并多余空格
    """
    cmds = "MLHVCSQTAZmlhvcsqtaz"
    # 命令字母前后紧跟数字时加空格
    d_attr = re.sub(f"(?<=\\d)([{cmds}])", r" \1", d_attr)
    d_attr = re.sub(f"([{cmds}])(?=\\d)", r"\1 ", d_attr)
    # 合并多个空格为一个
    d_attr = re.sub(r"\s+", " ", d_attr)
    return d_attr.strip()


def export_svg_for_glyph_dynamic(font, glyph_name, out_svg_path, scale_size=1024):
    """
    导出单个字形为 SVG 文件，动态 viewBox
    - 自动计算字形边界
    - 按最长边缩放到 scale_size
    - 翻转 Y 轴使 SVG 正向显示
    - path 数据经过四舍五入和命令字母空格优化
    """
    glyph_set = font.getGlyphSet()
    g = glyph_set[glyph_name]

    xmin, ymin, xmax, ymax = get_glyph_bounds(font, glyph_name)
    width = xmax - xmin
    height = ymax - ymin
    if width == 0 or height == 0:
        width = height = scale_size  # 防止空路径

    # 缩放比例：最长边缩放到 scale_size
    scale = scale_size / max(width, height)

    # 仿射变换: scale + 翻转y + 平移
    a, b, c, d = scale, 0.0, 0.0, -scale
    e, f = -xmin*scale, ymax*scale
    transform = (a, b, c, d, e, f)

    # 绘制 path
    path_pen = SVGPathPen(glyph_set)
    tpen = TransformPen(path_pen, transform)
    g.draw(tpen)
    d_attr = path_pen.getCommands().strip()
    d_attr = round_path_data(d_attr)
    d_attr = add_space_around_commands(d_attr)
    if not d_attr:
        d_attr = "M0 0"

    svg_content = (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(width*scale)} {int(height*scale)}" '
        f'width="{int(width*scale)}" height="{int(height*scale)}">\n'
        f'  <path d="{d_attr}" fill="black" />\n'
        f'</svg>\n'
    )

    with open(out_svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

def export_jpg_by_pillow(ttf_path, char, out_jpg_path, img_size_px):
    """
    使用 Pillow 绘制单字符 JPG
    - 图像大小为 img_size_px
    - 字体大小取 img_size 的 0.75 倍
    - 字符居中绘制
    """
    font_size = int(img_size_px*0.75)
    pil_font = ImageFont.truetype(ttf_path, size=font_size)
    img = Image.new("RGB", (img_size_px, img_size_px), "white")
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0,0), char, font=pil_font)
    w = bbox[2]-bbox[0]; h = bbox[3]-bbox[1]
    x = (img_size_px - w)//2 - bbox[0]
    y = (img_size_px - h)//2 - bbox[1]
    draw.text((x,y), char, font=pil_font, fill="black")
    img.save(out_jpg_path, "JPEG", quality=95)

def process_font_file(ttf_path, char_list, outdir, svg_scale=1024, img_size=512, export_jpg=False):
    """
    处理单个字体文件：
    - 遍历 stokes.json 字符顺序
    - 导出 SVG 和可选 JPG
    - 跳过字体中不存在的字符
    """
    font = TTFont(ttf_path)
    cmap = font.getBestCmap()
    font_basename = os.path.splitext(os.path.basename(ttf_path))[0]
    svg_dir = os.path.join(outdir, font_basename, "svg")
    jpg_dir = os.path.join(outdir, font_basename, "jpg") if export_jpg else None
    os.makedirs(svg_dir, exist_ok=True)
    if export_jpg:
        os.makedirs(jpg_dir, exist_ok=True)

    for char in tqdm(char_list, desc=f"{font_basename}", unit="char"):
        cp = ord(char)
        if cp not in cmap:
            continue
        glyph_name = cmap[cp]
        filename_base = safe_name_for_file(char, cp)
        try:
            svg_path = os.path.join(svg_dir, f"{filename_base}.svg")
            export_svg_for_glyph_dynamic(font, glyph_name, svg_path, svg_scale)
            if export_jpg:
                jpg_path = os.path.join(jpg_dir, f"{filename_base}.jpg")
                export_jpg_by_pillow(ttf_path, char, jpg_path, img_size)
        except Exception as e:
            print(f"错误 {char}: {e}")
    font.close()

def main():
    """
    主函数：
    - 解析命令行参数
    - 读取 stokes.json
    - 遍历字体目录，调用 process_font_file 导出字符
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts-dir", default=FONTS_DIR, help="字体文件目录（TTF/OTF/TTC）")
    ap.add_argument("--stokes-json", default=stokes_FILE, help="stokes.json 文件路径")
    ap.add_argument("--outdir", default="output", help="输出根目录")
    ap.add_argument("--svg-scale", type=int, default=1024, help="SVG 最大边长度")
    ap.add_argument("--img-size", type=int, default=512, help="JPG 图像大小（像素，若启用）")
    ap.add_argument("--jpg", action="store_true", help="同时导出 JPG（Pillow 绘制）")
    args = ap.parse_args()

    with open(args.stokes_json, "r", encoding="utf-8") as f:
        stokes_data = json.load(f)
    char_list = list(stokes_data.keys())  # 保持 JSON 顺序

    # 遍历字体
    font_files = [os.path.join(root, file)
                  for root, dirs, files in os.walk(args.fonts_dir)
                  for file in files if file.lower().endswith((".ttf", ".otf", ".ttc"))]

    for font_path in tqdm(font_files, desc="Fonts", unit="font"):
        process_font_file(font_path, char_list, args.outdir,
                          svg_scale=args.svg_scale, img_size=args.img_size,
                          export_jpg=args.jpg)

if __name__ == "__main__":
    main()

# python font2svg_batch_dynamic_viewbox.py --fonts-dir ../fonts --stokes-json ./stokes.json --outdir ./output --svg-scale 1024 --img-size 512 --jpg