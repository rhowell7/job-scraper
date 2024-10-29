from main import parse_company_size


def test_parse_company_size():
    result = parse_company_size("1 to 50 Employees")
    assert result == "1-50"
    result = parse_company_size("51 to 200 Employees")
    assert result == "51-200"
    result = parse_company_size("201 to 500 Employees")
    assert result == "201-500"
    result = parse_company_size("501 to 1K Employees")
    assert result == "501-1000"
    result = parse_company_size("1K to 5K Employees")
    assert result == "1000-5000"
    result = parse_company_size("5K to 10K Employees")
    assert result == "5000-10000"
    result = parse_company_size("10K+ Employees")
    assert result == "10000+"
