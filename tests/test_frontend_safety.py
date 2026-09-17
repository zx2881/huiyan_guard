from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def test_report_does_not_render_model_text_with_inner_html():
    report_script = (FRONTEND / "assets" / "js" / "report.js").read_text(
        encoding="utf-8"
    )
    assert "innerHTML" not in report_script
    assert "textContent" in report_script


def test_upload_script_previews_and_limits_long_edge():
    upload_script = (FRONTEND / "assets" / "js" / "upload.js").read_text(
        encoding="utf-8"
    )
    assert "createImageBitmap" in upload_script
    assert "1600" in upload_script
    assert '"image/jpeg"' in upload_script


def test_history_and_report_use_safe_dom_and_print_styles():
    report_script = (FRONTEND / "assets" / "js" / "report.js").read_text(
        encoding="utf-8"
    )
    history_script = (FRONTEND / "assets" / "js" / "records.js").read_text(
        encoding="utf-8"
    )
    styles = (FRONTEND / "assets" / "css" / "common.css").read_text(
        encoding="utf-8"
    )
    assert "innerHTML" not in report_script
    assert "innerHTML" not in history_script
    assert "@media print" in styles
    assert "window.print()" in report_script
    assert "内部复核" in report_script
    assert '"reviewing"' in report_script
    assert "离线历史回放" in report_script
    assert "不能作为实时识别或准确率证明" in report_script
