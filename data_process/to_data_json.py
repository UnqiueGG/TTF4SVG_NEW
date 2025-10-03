#!/usr/bin/env python3
"""
output_to_json.py
将 output 目录下的每个字体的 SVG/JPG 导出文件按 stokes.json 顺序转成指定 JSON 格式
- 按 stokes.json 中字符顺序
- 如果字体中缺少某字则跳过该字体
- 输出 JSON 可直接用于聊天问答场景
- 带进度条显示处理进度
- 路径统一使用 '/' 分隔符
"""

import os
import json
import re
import unicodedata
from tqdm import tqdm

OUTPUT_DIR = "./output"
STOKES_FILE = "./stokes.json"
OUTPUT_JSON = "./output.json"

def safe_name_for_file(char, cp=None):
    """
    与生成 SVG/JPG 时相同的文件安全命名
    """
    if cp is None:
        cp = ord(char)
    bad_chars = r'[/\\:*?"<>|]'
    if re.search(bad_chars, char):
        return f"U+{cp:04X}"
    cat = unicodedata.category(char)
    if cat.startswith("C") or char.isspace():
        return f"U+{cp:04X}"
    return char

def load_stokes_chars(stokes_path):
    """读取 stokes.json 字符顺序"""
    with open(stokes_path, "r", encoding="utf-8") as f:
        stokes_data = json.load(f)
    return list(stokes_data.keys())

def find_fonts(output_dir):
    """列出 output 下所有字体目录"""
    fonts = [d for d in os.listdir(output_dir)
             if os.path.isdir(os.path.join(output_dir, d))]
    return fonts

def build_json_for_char(char, fonts, output_dir):
    """
    构建指定字符的 JSON 数据列表
    - 如果字体缺少该字符的 svg 或 jpg 文件，则跳过该字体
    """
    items = []

    for font_name in fonts:
        font_dir = os.path.join(output_dir, font_name)
        svg_path = os.path.join(font_dir, "svg", f"{safe_name_for_file(char)}.svg").replace("\\", "/")
        jpg_path = os.path.join(font_dir, "jpg", f"{safe_name_for_file(char)}.jpg").replace("\\", "/")

        # 如果任意一个文件不存在就跳过
        if not os.path.exists(svg_path) or not os.path.exists(jpg_path):
            continue

        messages = [
            {"content": "<image>这个图片上是什么风格的字体，并且请你识别是什么字？", "role": "user"},
            {"content": f"这个字是{font_name}风格的，它是'{char}'字", "role": "assistant"},
            {"content": "我需要这张图片上字体的SVG代码，请你生成。", "role": "user"},
            {"content": open(svg_path, "r", encoding="utf-8").read(), "role": "assistant"},
        ]

        item = {
            "messages": messages,
            "images": [jpg_path]
        }

        items.append(item)
    return items

def main():
    char_list = load_stokes_chars(STOKES_FILE)
    fonts = find_fonts(OUTPUT_DIR)

    output_data = []

    for char in tqdm(char_list, desc="Chars", unit="char"):
        items_for_char = build_json_for_char(char, fonts, OUTPUT_DIR)
        if items_for_char:
            output_data.extend(items_for_char)  # 每个字体单独一个 entry
        # 如果没有字体包含该字，直接跳过

    # 写入 JSON 文件
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"已生成 JSON 文件: {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
