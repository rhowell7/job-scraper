from main import extract_salary


def test_basic_salary_range():
    result = extract_salary(
        "The range for this role is $140,000–$350,000 cash, $10,000–$5,000,000 in equity."  # noqa: E501
    )
    assert result == (140000, 350000)


def test_single_salary():
    result = extract_salary(
        "The expected salary for this position is $120,000 USD."
    )
    assert result == (120000, None)


def test_multiple_salaries():
    result = extract_salary(
        "USA-based roles only: The Annual base salary for this role is between $121,000 USD and $163,000 USD, plus immediate participation in 1Password's benefits program... Canada-based roles only: The Annual base salary for this role is between $109,000 CAD and $147,000 CAD, plus immediate participation in 1Password’s generous benefits program"  # noqa: E501
    )
    assert result == (121000, 163000)


def test_no_salary():
    result = extract_salary("This is an equity-only position.")
    assert result == (None, None)


def test_long_text():
    result = extract_salary(
        "The expected salary range for this position is $102,000 to $131,000 CAD"
    )
    assert result == (102000, 131000)


def test_parenthesis():
    result = extract_salary("Current base salary range: ($160,000 - $180,000).")
    assert result == (160000, 180000)


def test_spaces():
    result = extract_salary(
        "California/Colorado/Hawaii/New Jersey/New York/Washington/DC pay range $98,000 - $210,000 USD"  # noqa: E501
    )
    assert result == (98000, 210000)


def test_hyphen():
    result = extract_salary("Pay Range: $149,500—$149,500 CAD")
    assert result == (149500, 149500)


def test_wide_range():
    result = extract_salary(
        "The salary range for this role is $1,000 - $100,000,000 USD."
    )
    assert result == (1000, 100000000)
