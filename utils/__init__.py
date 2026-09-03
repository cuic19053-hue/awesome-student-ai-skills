# -*- coding: utf-8 -*-
"""
awesome-student-ai-skills / utils
================================

共享工具包：为 22+ 个子 skill 提供统一的 docx 生成与 PDF 输出能力。

当前提供：

    - docx_common : docx 生成基础库（字体常量/页面/段落/表格/页眉页脚/DocxBuilder 基类）
    - pdf_export  : docx → PDF 转换、PDF 合并、页码、水印、元数据、完整性校验

使用方式：
    from utils.docx_common import DocxBuilder, add_title, add_paragraph
    builder = DocxBuilder("/tmp/test.docx")
    builder.add_title("测试标题")
    builder.add_paragraph("正文段落。")
    builder.save()

    from utils.pdf_export import docx_to_pdf, merge_pdfs
    pdf_path = docx_to_pdf("/tmp/test.docx")
    merge_pdfs(["A.docx.pdf", "B.docx.pdf"], "/tmp/merged.pdf")
"""

__all__ = ["docx_common", "pdf_export"]
__version__ = "1.1.0"
