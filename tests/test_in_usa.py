import pytest
from main import in_usa


def test_in_usa():
    result = in_usa("Remote, Canada")
    assert result == False

def test_in_usa2():
    result = in_usa("Remote, USA")
    assert result == True

def test_uk():
    result = in_usa("Cardiff, London or Remote (UK)")
    assert result == False

def test_uk():
    result = in_usa("Remote, APAC")
    assert result == False
