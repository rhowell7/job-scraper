from main import clean_text


def test_clean_text():
    result = clean_text("Hello\xa0world!\n\n\nHow are you?")
    assert result == "Hello world!\nHow are you?"
