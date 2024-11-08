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


def test_many_locs():
    result = in_usa(
        "Argentina; Brazil; LATM; Ireland; United Kingdom; Spain; Italy; Poland; Czech Republic; Bulgaria; Netherlands; Slovakia; Hungary"  # noqa: E501
    )
    assert result is False


def test_many_locs2():
    result = in_usa("Dublin; Amsterdam; Poland; Brazil")
    assert result is False


def test_remote_poland():
    result = in_usa("Remote Poland")
    assert result is False


def test_remote():
    result = in_usa("Remote")
    assert result is True


def test_cyprus():
    result = in_usa("Pora.ai Cyprus or remote")
    assert result is False


def test_remote_emea():
    result = in_usa("Remote, EMEA")
    assert result is False


def test_naperville():
    result = in_usa("Naperville, IL or Remote")
    assert result is True


def test_argentina():
    result = in_usa("Buenos Aires")
    assert result is False
