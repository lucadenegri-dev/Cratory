from app.integrations.integrity import IntegrityResult, check_file, parse_result


def test_parse_clean_decode_is_ok():
    r = parse_result(0, "")
    assert r.ok is True
    assert r.detail is None


def test_parse_nonzero_exit_is_corrupt():
    r = parse_result(1, "")
    assert r.ok is False


def test_parse_stderr_errors_is_corrupt_with_detail():
    r = parse_result(0, "[flac @ 0x..] Invalid data found when processing input")
    assert r.ok is False
    assert "Invalid data" in r.detail


def test_check_file_uses_injected_runner():
    def fake_runner(path, timeout):
        return (0, "")  # (returncode, stderr)
    r = check_file("/whatever.flac", runner=fake_runner)
    assert r == IntegrityResult(ok=True, detail=None)


def test_check_file_timeout_is_corrupt():
    def fake_runner(path, timeout):
        raise TimeoutError()
    r = check_file("/whatever.flac", runner=fake_runner)
    assert r.ok is False
    assert r.detail == "timeout"
