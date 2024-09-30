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


def test_salary_after_funding():
    result = extract_salary(
        "About HackerRank:\nHackerRank is a Y Combinator alumnus backed by tier-one Silicon Valley VCs with total funding of over $100 million. The HackerRank Developer Skills Platform is the standard for assessing developer skills for 2,500+ companies across industries and 23M+ developers worldwide. Companies like LinkedIn, Stripe, and Peloton rely on HackerRank to objectively evaluate skills against millions of developers at every hiring process, allowing teams to hire the best and reduce engineering time. Developers rely on HackerRank to turn their skills into great jobs. We’re data-driven givers who take full ownership of our work and love delighting our customers!\nHackerRank is a proud equal employment opportunity and affirmative action employer. We provide equal opportunity to everyone for employment based on individual performance and qualification. We never discriminate based on race, religion, national origin, gender identity or expression, sexual orientation, age, marital, veteran, or disability status. All your information will be kept confidential according to EEO guidelines.\nWe offer a comprehensive total rewards package where you’ll be rewarded based on your performance and recognized for the value you bring to the business.\nTotal compensation and benefits consist of salary, quarterly performance incentives, equity (stock options), medical, dental, vision, life insurance, travel insurance, monthly work-from-home stipend, learning and development reimbursements, flexible remote-first work culture, 401(K), flexible time off, generous parental leave and more. Under our flexible paid time off policy, you’ll decide how much time you need based on your circumstances.\nCurrent base salary range: ($160,000 - $180,000). The exact salary may vary based on skills, experience, location, market ranges, and other compensation offered. The salary range does not include other compensation components, commission (for sales-related roles), bonuses, or benefits for which you may be eligible. Salary may be adjusted based on business needs.\nNotice to prospective HackerRank job applicants:\nWe’ve noticed fake accounts posing as HackerRank Recruiters on Linkedin and through text. These imposters trick you into paying them for jobs/providing credit check information.\nHere’s how to spot the real deal:\nOur Recruiters use @hackerrank.com email addresses.\nWe never ask for payment or credit check information to apply, interview, or work here.\nThanks for your interest in HackerRank!\n#LI-Remote'"  # noqa: E501
    )
    assert result == (160000, 180000)
