import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse, urlunparse
import psycopg2
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
from locations import allow_keywords, states_and_cities, exclude_keywords
from dotenv import load_dotenv
import os


load_dotenv()
# Load API key and custom search engine (cx) from Google
API_KEY = os.getenv("API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
# Load PostgresQL credentials from the .env file
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

# Load the dictionary into a set for fast keyword lookups
with open("dict/words") as f:
    dictionary = set(word.strip().lower() for word in f)


# Preferences for scoring (positive/negative keywords)
preferences = {
    "Remote": 10,
    "Python": 10,
    "Machine Learning": 8,
    "Backend": 8,
    "Linux": 9,
    "Golang": 6,
    "Go": 6,
    "Java": -10,
    "Haskell": -8,
    "iOS": -7,
    "Hybrid": -10,
    "On-site": -10,
}


def google_custom_search(query, num=3):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"q": query, "key": API_KEY, "cx": SEARCH_ENGINE_ID, "num": num}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        return None


def normalize_url(url):
    parsed = urlparse(url)
    # Reconstruct the URL without query parameters
    normalized = parsed._replace(query="")
    return urlunparse(normalized)


def in_usa(location):
    location = location.lower()

    delimiters = [",", "/", "-", "(", ")", " "]  # Split by space or no?
    pattern = "|".join(map(re.escape, delimiters))
    words = re.split(pattern, location)

    # Check if any part of the location matches an exclude keyword
    for word in words:
        if word.strip() in exclude_keywords:
            return False

    # Check if any part of the location matches an allow keyword or US city/state
    for word in words:
        if word.strip() in allow_keywords or word.strip() in states_and_cities:
            return True

    return True  # If no match is found, default to including the job


def clean_text(text):
    # Replace non-breaking space with a normal space
    text = text.replace("\xa0", " ")
    # Replace multiple newlines with a single newline
    text = re.sub(r"\n+", "\n", text)
    # Trim leading/trailing spaces
    text = "\n".join(line.strip() for line in text.splitlines())
    return text


def extract_keywords(text):
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text)  # len>=3 to avoid "you'll"
    keyword_dict = {}
    for word in words:
        lower_word = word.lower()
        if lower_word not in dictionary:
            # Always keep the first occurrence's case (either lower or upper)
            if lower_word not in keyword_dict:
                keyword_dict[lower_word] = word

    # Return a sorted set of keywords (keeping original case)
    return sorted(keyword_dict.values(), key=lambda word: word.lower())


def extract_job_info(url):
    job_info = {}
    try:
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            full_title = soup.title.string.strip() if soup.title else None

            # Initialize job details with default values
            job_info["job_title"] = None
            job_info["company_name"] = None
            job_info["location"] = None
            job_info["description"] = None

            # Greenhouse job board
            if "greenhouse" in url:
                # GH pattern: "Job Application for [Job Title] at [Company Name]"
                match = re.match(r"Job Application for (.+) at (.+)", full_title)
                if match:
                    job_info["job_title"] = match.group(1).strip()
                    job_info["company_name"] = match.group(2).strip()

                pattern = re.compile(
                    r'"job_post_location":"(.*?)",'
                    r'"public_url":"(.*?)",'
                    r'"company_name":"(.*?)"'
                )
                match = pattern.search(response.text)

                if match:
                    job_info["location"] = match.group(1)

                    # Extract the job description from the specific div class
                    job_description_div = soup.find(
                        "div", class_="job__description body"
                    )
                    if job_description_div:
                        raw_text = job_description_div.get_text(separator="\n")
                        job_info["description"] = clean_text(raw_text)
                else:
                    print(f"  177: Failed to extract job details from {url}")
                    return None

            # Lever job board
            elif "lever" in url:
                # Lever pattern: "[Company Name] - [Job Title]"
                parts = full_title.split(" - ", 1)
                if len(parts) == 2:
                    job_info["company_name"] = parts[0].strip()
                    job_info["job_title"] = parts[1].strip()

                # Extract the location
                location_tag = soup.find("div", class_="posting-category")
                if location_tag:
                    job_info["location"] = location_tag.text.strip()

                # Extract the job description
                job_description_tag = soup.find(
                    "div", attrs={"data-qa": "job-description"}
                )
                if job_description_tag:
                    raw_text = job_description_tag.get_text(separator="\n")
                    job_info["description"] = clean_text(raw_text)

            return job_info

        else:
            print(f"  203: Failed to retrieve page {url}: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"  206: HTTP request failed: {e}")
        return None


def score_job(title, description):
    score = 0
    title = title.lower()
    description = description.lower()
    preference_hits = []

    # Add or subtract points based on preferences
    for keyword, value in preferences.items():
        # Match whole words only, e.g. Java in "JavaScript" should not match
        pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
        if pattern.search(title) or pattern.search(description):
            preference_hits.append(keyword)
            score += value

    return score, preference_hits


def extract_salary(description):
    # Find the first two salary values after the '$' symbols
    salary_pattern = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*)")
    matches = salary_pattern.findall(description)

    if len(matches) >= 2:
        # If at least two salaries are found, return them as min and max
        min_salary = int(matches[0].replace(",", ""))
        max_salary = int(matches[1].replace(",", ""))
        return min_salary, max_salary

    elif len(matches) == 1:
        # If only one salary is found, return it as the min; max=None
        min_salary = int(matches[0].replace(",", ""))
        return min_salary, None

    return None, None


def get_glassdoor_data_from_db(company_name):
    """
    Check if Glassdoor data for the given company exists in the database.
    """
    cursor.execute(
        "SELECT glassdoor_rating, glassdoor_link, glassdoor_num_reviews, "
        "company_size "
        "FROM glassdoor_data "
        "WHERE company = %s",
        (job_info["company_name"],),
    )
    result = cursor.fetchone()
    if result:
        return {
            "rating": result[0],
            "glassdoor_url": result[1],
            "reviews": result[2],
            "company_size": result[3],
        }
    return None


def save_glassdoor_data_to_db(company_name, glassdoor_data):
    """
    Save Glassdoor data to the database.
    """
    cursor.execute(
        "INSERT INTO glassdoor_data (company, glassdoor_rating, glassdoor_link, "
        "glassdoor_num_reviews, company_size) "
        "VALUES (%s, %s, %s, %s, %s)",
        (
            company_name,
            glassdoor_data["rating"],
            glassdoor_data["glassdoor_url"],
            glassdoor_data["reviews"],
            glassdoor_data["company_size"],
        ),
    )
    conn.commit()


def scrape_glassdoor_data(company_name):
    """
    Scrape Glassdoor data for the given company using Selenium.
    """
    # Set up Chrome options to run headless
    chrome_options = Options()
    # chrome_options.add_argument("--headless")  # Uncomment to run headless

    # Set up the Chrome driver
    service = Service("/usr/local/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        # Search for the company on Glassdoor
        search_url = (
            "https://www.glassdoor.com/Search/results.htm?"
            f"keyword={company_name.replace(' ', '%20')}"
        )
        driver.get(search_url)
        time.sleep(2)

        try:
            first_company_tile = driver.find_element(By.CLASS_NAME, "company-tile")

            # Extract the Glassdoor rating
            try:
                rating = (
                    first_company_tile.find_element(
                        By.CSS_SELECTOR, "strong.small.css-b63kyi"
                    )
                    .text.strip()
                    .replace(" ★", "")
                )
            except Exception:
                rating = "N/A"

            # Extract the number of reviews
            try:
                reviews_span = first_company_tile.find_elements(
                    By.XPATH, ".//span[contains(text(),'Reviews')]"
                )[0]
                reviews = reviews_span.find_element(
                    By.XPATH, "./preceding-sibling::span"
                ).text.strip()
            except Exception:
                reviews = "N/A"

            # Extract the company size
            try:
                company_size = first_company_tile.find_element(
                    By.XPATH, ".//span[contains(text(),'Employees')]"
                ).text.strip()
            except Exception:
                company_size = "N/A"

            # Extract the Glassdoor URL for the company
            try:
                glassdoor_url = first_company_tile.get_attribute("href")
                # glassdoor_url = 'https://www.glassdoor.com' + link
            except Exception:
                glassdoor_url = "N/A"

        except Exception:
            # If company tile is not found, return a message
            return {"error": f"No company data found for {company_name}"}

        # Create a dictionary to hold the extracted data
        glassdoor_data = {
            "rating": rating,
            "reviews": reviews,
            "company_size": company_size,
            "glassdoor_url": glassdoor_url,
        }
        return glassdoor_data

    finally:
        driver.quit()


if __name__ == "__main__":
    # Connect to PostgreSQL
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST
    )
    cursor = conn.cursor()

    query = (
        "(intitle:engineer OR intitle:software OR intitle:python OR "
        "intitle:developer OR intitle:data) "
        '(python OR backend OR ml OR "machine learning") '
        "site:lever.co OR site:greenhouse.io "
        "-intitle:staff -intitle:senior -intitle:manager -intitle:lead "
        '-intitle:principal -intitle:director "Remote"'
    )

    results = google_custom_search(query, 10)

    # Deduplicate URLs, if they already exist in `jobs` or `foreign_jobs` tables
    cursor.execute("SELECT url FROM jobs")
    existing_urls = set(url for url, in cursor.fetchall())
    cursor.execute("SELECT url FROM foreign_jobs")
    foreign_urls = set(url for url, in cursor.fetchall())

    if results:
        for item in results.get("items", []):
            print("Processing URL:", item["link"])
            title = item["title"]
            url = normalize_url(item["link"])

            # Skip duplicate URLs
            if url in existing_urls:
                print(f"  370: Skipping duplicate US job: {title}")
                continue
            elif url in foreign_urls:
                print(f"  373: Skipping duplicate foreign job: {title}")
                continue

            job_info = extract_job_info(url)
            if (
                not job_info
                or not job_info["job_title"]
                or not job_info["company_name"]
            ):
                print(f"  378: Failed to extract job and company from {url}")
                continue

            # Skip jobs outside the USA
            if not in_usa(job_info["location"]):
                print("  383: Skipping job outside the USA:")
                print(f"    Location: {job_info['location']}")
                print(f"    URL: {url}")
                print(f"    Title: {job_info['job_title']}")
                print(f"    Company: {job_info['company_name']}")
                cursor.execute(
                    "INSERT INTO foreign_jobs (url, company, job_title, "
                    "location, date_first_seen) "
                    "VALUES (%s, %s, %s, %s, CURRENT_DATE)",
                    (
                        url,
                        job_info["company_name"],
                        job_info["job_title"],
                        job_info["location"],
                    ),
                )
                conn.commit()
                continue

            score, preference_hits = score_job(
                job_info["job_title"], job_info["description"]
            )
            salary_min, salary_max = extract_salary(job_info["description"])
            keywords = extract_keywords(job_info["description"])

            # Get or scrape Glassdoor data
            company = job_info["company_name"]
            glassdoor_data = get_glassdoor_data_from_db(company)

            if glassdoor_data is None:
                print(f"  405: Scraping Glassdoor data for {company}")
                glassdoor_data = scrape_glassdoor_data(company)
                save_glassdoor_data_to_db(job_info["company_name"], glassdoor_data)
            else:
                print(f"  409: Using cached Glassdoor data for {company}")

            cursor.execute(
                """
                INSERT INTO jobs (
                    company, job_title, date_first_seen, salary_min, salary_max,
                    location, url, glassdoor_rating, glassdoor_link,
                    glassdoor_num_reviews, company_size, score, preference_hits,
                    keywords
                )
                VALUES (
                    %s, %s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    job_info["company_name"],
                    job_info["job_title"],
                    salary_min,
                    salary_max,
                    job_info["location"],
                    url,
                    glassdoor_data["rating"],
                    glassdoor_data["glassdoor_url"],
                    glassdoor_data["reviews"],
                    glassdoor_data["company_size"],
                    score,
                    preference_hits,
                    keywords,
                ),
            )
            conn.commit()
            print(f"  417: Job added to the database: {job_info['job_title']}")

    cursor.close()
    conn.close()
