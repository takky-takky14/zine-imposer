def impose_pdf(
    input_bytes: bytes,
    gutter_mm: float = 0.0,
    outer_margin_mm: float = 0.0,
    auto_pad_blank: bool = True,
    flip_back_side: bool = True,
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

    for i, placement in enumerate(placements):
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

            merge_page_into_slot(
                dest_page,
                left_page,
                left_slot_x,
                slot_y,
                slot_w,
                slot_h,
                align="inner-left",
            )

        # 右ページ
        if placement.right is not None:
            if placement.right < original_count:
                right_page = reader.pages[placement.right]
            else:
                right_page = create_blank_like(first_w, first_h)

            merge_page_into_slot(
                dest_page,
                right_page,
                right_slot_x,
                slot_y,
                slot_w,
                slot_h,
                align="inner-right",
            )

        # 面付け後PDFの偶数ページ（2,4,6...）＝裏面だけ 180度回転
        if flip_back_side and (i + 1) % 2 == 0:
            dest_page.rotate(180)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)

    return output.read(), placements, original_count, final_count
