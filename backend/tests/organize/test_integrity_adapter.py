from app.organize.integrations.integrity import IntegrityResult, check_file, parse_result


def test_parse_clean_decode_is_ok():
    r = parse_result(0, "")
    assert r.ok is True
    assert r.detail is None


def test_parse_nonzero_exit_is_corrupt():
    # exit != 0 = ffmpeg non riesce a decodificare (illeggibile/troncato)
    r = parse_result(1, "")
    assert r.ok is False


def test_parse_benign_header_missing_is_ok():
    # 'Header missing' a inizio MP3: intoppo transitorio, il file suona -> ok
    err = ("[mp3float @ 0x0] Header missing\n"
           "[aist#0:0/mp3 @ 0x0] Error submitting packet to decoder: "
           "Invalid data found when processing input")
    r = parse_result(0, err)
    assert r.ok is True
    assert r.detail is None


def test_parse_cover_art_error_is_ok():
    # errore sullo stream copertina (immagine), non sull'audio -> ok
    r = parse_result(0, "[png @ 0x0] Invalid PNG signature 0xFFD8FFE000104A46.")
    assert r.ok is True


def test_parse_real_frame_corruption_is_corrupt():
    err = ("[flac @ 0x0] invalid residual\n"
           "[flac @ 0x0] decode_frame() failed")
    r = parse_result(0, err)
    assert r.ok is False
    assert "invalid residual" in r.detail


def test_parse_flac_sync_error_is_corrupt():
    r = parse_result(0, "[flac @ 0x0] invalid sync code")
    assert r.ok is False


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
