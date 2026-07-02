from seo_advisor.demo import run_demo_scan


def test_demo_scan_produces_all_three_reports(tmp_path):
    outcome = run_demo_scan(out_dir=str(tmp_path / "demo-report"))

    assert outcome.beginner_path.exists()
    assert outcome.technical_path.exists()
    assert outcome.json_path.exists()


def test_demo_scan_finds_known_issues(tmp_path):
    # demo_assets/bad_site 刻意包含多種常見問題，demo 模式應該能找到它們，
    # 這樣新手第一次執行 demo 時才能看到「有內容」的報告。
    outcome = run_demo_scan(out_dir=str(tmp_path / "demo-report"))

    assert len(outcome.report.findings) > 0
    assert outcome.report.site_health_score < 100


def test_demo_scan_progress_mentions_sample_data(tmp_path):
    messages: list[str] = []
    run_demo_scan(out_dir=str(tmp_path / "demo-report"), on_progress=messages.append)

    assert any("示範" in msg for msg in messages)
