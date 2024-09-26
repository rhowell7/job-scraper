from main import in_usa


def test_in_usa():
    result = in_usa("Remote, Canada")
    assert result is False


def test_in_usa2():
    result = in_usa("Remote, USA")
    assert result is True


def test_uk():
    result = in_usa("Cardiff, London or Remote (UK)")
    assert result is False


def test_apac():
    result = in_usa("Remote, APAC")
    assert result is False


def test_unknown():
    result = in_usa("Neverheardofit")
    assert result is True
