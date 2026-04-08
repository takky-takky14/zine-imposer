import io
from dataclasses import dataclass
from typing import List, Tuple, Optional

import streamlit as st
from pypdf import PdfReader, PdfWriter, Transformation


# =========================
# 定数
# =========================
MM_TO_PT = 72 / 25.4

# A4横（pt）
A4_LANDSCAPE_WIDTH = 841.8898
A4_LANDSCAPE_HEIGHT = 595.2756


@dataclass
class Placement:
    left: Optional[int]   # 0-based page index, None = blank
    right: Optional[int]  # 0-based page index, None = blank
    label: str            # "1枚目 表" など


def mm_to_pt(mm: float) -> float:
    return mm * MM_TO_PT


def build_booklet_pairs(page_count: int) -> List[Tuple[int, int]]:
    """
    中綴じ面付け用のページペアを返す。
    12ページなら:
    [(11,0), (1,10), (9,2), (3,8), (7,4), (5,6)]
    """
    pairs: List[Tuple[int, int]] = []
    left = page_count
    right = 1

    while left > right:
        # 表面
        pairs.append((left - 1, right - 1))
        left -= 1
        right += 1

        # 裏面
        pairs.append((right - 1, left - 1))
        left -= 1
        right += 1

    return pairs


def pad_to_multiple_of_four(page_count: int) -> int:
    rem = page_count % 4
    return page_count if rem == 0 else page_count + (4 - rem)


def build_placements(page_count: int) -> List[Placement]:
    pairs = build_booklet_pairs(page_count)
    placements: List[Placement] = []

    sheet_num = 1
    for i, (l, r) in enumerate(pairs):
        side = "表" if i % 2 == 0 else "裏"
        placements.append(
            Placement(
                left=l,
                right=r,
                label=f"{sheet_num}枚目 {side}",
            )
        )
        if i % 2 == 1:
            sheet_num += 1

    return placements


def get_page_size(page) -> Tuple[float, float]:
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    return width, height


def merge_page_into_slot(
    dest_page,
    src_page,
    slot_x: float,
    slot_y: float,
    slot_w: float,
    slot_h: float,
):
    """
    src_page を slot に収まるよう縮小・平行移動して配置する。
    ここでは回転なし（A5縦をA4横の左右半分に置く想定）。
    """
    src_w, src_h = get_page_size(src_page)

    scale = min(slot_w / src_w, slot_h / src_h)

    placed_w = src_w * scale
    placed_h = src_h * scale

    tx = slot_x + (slot_w - placed_w) / 2
    ty = slot_y + (slot_h - placed_h) / 2

    transform = Transformation().scale(scale).translate(tx, ty)
    dest_page.merge_transformed_page(src_page, transform)


def create_blank_like(page_width: float, page_height: float):
    writer = PdfWriter()
    return writer.add_blank_page(width=page_width, height=page_height)


def impose_pdf(
    input_bytes: bytes,
    gutter_mm: float = 6.0,
    outer_margin_mm: float = 5.0,
    auto_pad_blank: bool = True,
) -> Tuple[bytes, List[Placement], int, int]:
    """
    入力PDFを面付けして A4横PDF を返す。
    戻り値:
      output_pdf_bytes, placements, original_page_count, final_page_count
    """
    reader = PdfReader(io.BytesIO(input_bytes))

    if reader.is_encrypted:
        raise ValueError("暗号化されたPDFには対応していません。")

    original_count = len(reader.pages)
    if original_count == 0:
        raise ValueError("ページが読み取れません。")

    final_count = original_count
    if original_count % 4 != 0:
        if not auto_pad_blank:
            raise ValueError("ページ数が4の倍数ではありません。白紙追加をONにしてください。")
        final_count = pad_to_multiple_of_four(original_count)

    placements = build_placements(final_count)

    writer = PdfWriter()

    gutter = mm_to_pt(gutter_mm)
    outer_margin = mm_to_pt(outer_margin_mm)

    usable_width = A4_LANDSCAPE_WIDTH - outer_margin * 2
    usable_height = A4_LANDSCAPE_HEIGHT - outer_margin * 2

    slot_w = (usable_width - gutter) / 2
    slot_h = usable_height

    left_slot_x = outer_margin
    right_slot_x = outer_margin + slot_w + gutter
    slot_y = outer_margin

    # 白紙ページのサイズは、元PDFの1ページ目と同サイズに合わせる
    first_w, first_h = get_page_size(reader.pages[0])

    for placement in placements:
        dest_page = writer.add_blank_page(
            width=A4_LANDSCAPE_WIDTH,
            height=A4_LANDSCAPE_HEIGHT,
        )

        # 左ページ
        if placement.left is not None:
            if placement.left < original_count:
                left_page = reader.pages[placement.left]
            else:
                left_page = create_blank_like(first_w, first_h)
            merge_page_into_slot(dest_page, left_page, left_slot_x, slot_y, slot_w, slot_h)

        # 右ページ
        if placement.right is not None:
            if placement.right < original_count:
                right_page = reader.pages[placement.right]
            else:
                right_page = create_blank_like(first_w, first_h)
            merge_page_into_slot(dest_page, right_page, right_slot_x, slot_y, slot_w, slot_h)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)

    return output.read(), placements, original_count, final_count


def format_page_number(index: Optional[int], original_count: int) -> str:
    if index is None:
        return "白紙"
    if index >= original_count:
        return "白紙"
    return str(index + 1)


# =========================
# Streamlit UI
# =========================
st.set_page_config(page_title="Zine Imposer", layout="wide")

st.title("Zine Imposer")
st.caption("A5縦の単ページPDFをアップロードすると、中綴じ用のA4横PDFを生成します。")

left_col, right_col = st.columns([1.4, 1])

with left_col:
    uploaded_file = st.file_uploader("PDFファイルをアップロード", type=["pdf"])

with right_col:
    st.subheader("設定")
    gutter_mm = st.number_input("ノド余白（mm）", min_value=0.0, max_value=30.0, value=6.0, step=1.0)
    outer_margin_mm = st.number_input("外側余白（mm）", min_value=0.0, max_value=30.0, value=5.0, step=1.0)
    auto_pad_blank = st.toggle("4の倍数になるよう白紙を自動追加", value=True)

if uploaded_file is not None:
    try:
        file_bytes = uploaded_file.read()
        reader = PdfReader(io.BytesIO(file_bytes))

        if reader.is_encrypted:
            st.error("暗号化されたPDFには対応していません。")
            st.stop()

        original_count = len(reader.pages)
        if original_count == 0:
            st.error("ページが読み取れません。")
            st.stop()

        first_w, first_h = get_page_size(reader.pages[0])

        info_col1, info_col2, info_col3 = st.columns(3)
        info_col1.metric("元ページ数", original_count)
        info_col2.metric("先頭ページ幅(pt)", f"{first_w:.1f}")
        info_col3.metric("先頭ページ高(pt)", f"{first_h:.1f}")

        final_count = pad_to_multiple_of_four(original_count) if auto_pad_blank else original_count

        if final_count % 4 != 0:
            st.warning("ページ数が4の倍数ではありません。白紙追加をONにしてください。")
        else:
            placements = build_placements(final_count)

            st.subheader("面付け順プレビュー")
            for p in placements:
                l = format_page_number(p.left, original_count)
                r = format_page_number(p.right, original_count)
                st.write(f"- {p.label}: {l} / {r}")

            if st.button("面付けPDFを生成", type="primary"):
                output_bytes, placements, original_count, final_count = impose_pdf(
                    input_bytes=file_bytes,
                    gutter_mm=gutter_mm,
                    outer_margin_mm=outer_margin_mm,
                    auto_pad_blank=auto_pad_blank,
                )

                st.success("面付け済みPDFを生成しました。")

                out_name = uploaded_file.name.rsplit(".", 1)[0] + "_imposed_A4_landscape.pdf"

                st.download_button(
                    label="面付け済みPDFをダウンロード",
                    data=output_bytes,
                    file_name=out_name,
                    mime="application/pdf",
                )

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
else:
    st.info("まずは A5縦の単ページPDF をアップロードしてください。")
