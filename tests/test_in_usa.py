from main import in_usa


def test_in_usa_remote_canada():
    result = in_usa("Remote, Canada")
    assert result is False


def test_in_usa_remote_usa():
    result = in_usa("Remote, USA")
    assert result is True


def test_in_usa_multiple_countries():
    assert in_usa("Toronto, CAN, San Francisco, CA & Remote - US & Canada") is True


def test_germany_frankfurt():
    assert in_usa("Germany - Frankfurt") is False


def test_uk():
    result = in_usa("Cardiff, London or Remote (UK)")
    assert result is False


def test_apac():
    result = in_usa("Remote, APAC")
    assert result is False


def test_unknown():
    result = in_usa("Neverheardofit")
    assert result is True
