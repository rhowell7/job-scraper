import logging
import os
import re
import time
from typing import Dict, Tuple, List, Optional
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from locations import allow_locales, exclude_locales
from dotenv import load_dotenv

load_dotenv()


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            "logs/job_scraper.log", mode="a", encoding=None, delay=False
        ),
        logging.StreamHandler(),
    ],
)

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


def google_search(query: str, num_results: int = 100) -> List[str]:
    """
    Search using the Google Custom Search API and return result URLs.

    Args:
        query (str): The search query to perform.
        num (int): The number of results to return (default 100).

    Returns:
        List[str]: A list of normalized result URLs.
    """
    API_KEY = os.getenv("GOOGLE_API_KEY")
    SEARCH_ENGINE_ID = os.getenv("GOOGLE_CSE_ID")

    if not API_KEY or not SEARCH_ENGINE_ID:
        logging.error("Google API key or search engine ID not found.")
        raise EnvironmentError(
            "Missing GOOGLE_API_KEY or GOOGLE_CSE_ID environment variables. "
            + "Did you put them in your .env file?"
        )

    results = []
    start = 1

    while len(results) < num_results and start < 100:
        params = {
            "key": API_KEY,
            "cx": SEARCH_ENGINE_ID,
            "q": query,
            "start": start,
            "num": min(10, num_results - len(results)),
        }

        response = requests.get(
            "https://www.googleapis.com/customsearch/v1", params=params
        )

        if response.status_code != 200:
            logging.error(
                f"Google API error: {response.status_code} - {response.text}"
            )
            break

        data = response.json()
        if "items" not in data:
            logging.error(f"No search results found: {data}")
            break

        for item in data["items"]:
            link = item["link"]
            results.append(normalize_url(link))

        if "nextPage" not in data.get("queries", {}):
            break

        start += 10

    return results


def normalize_url(url: str) -> str:
    """
    Normalize the given URL by removing query parameters.

    Args:
        url (str): The URL to normalize.

    Returns:
        str: The normalized URL without query parameters.
    """
    parsed = urlparse(url)
    # Reconstruct the URL without query parameters
    normalized = parsed._replace(query="")
    url = urlunparse(normalized)
    url = re.sub(r"/apply$", "/", url)
    return url


def in_usa(location: str) -> bool:
    """
    Check if the given location is in the USA.

    Args:
        location (str): The location string.

    Returns:
        bool: True if the location is in the USA, False otherwise
    """
    logging.info(f"  Checking location: {location}")
    location = location.lower()

    delimiters = [",", "/", "-", "(", ")", "&", ";", " "]
    pattern = "|".join(map(re.escape, delimiters))
    words = re.split(pattern, location)

    # Check if any part of the location matches an exclude keyword
    for word in words:
        word = word.strip()
        if word in allow_locales:
            logging.info(f"  Allowed location found: {word}")
            return True

    for word in words:
        word = word.strip()
        if word in exclude_locales:
            logging.info(f"  Excluded location found: {word}")
            return False

    return True  # If no match is found, default to including the job


def clean_text(text: str) -> str:
    """
    Clean up the given text by replacing non-breaking spaces and multiple newlines.

    Args:
        text (str): The text to clean up.

    Returns:
        str: The cleaned text.
    """
    # Replace non-breaking space with a normal space
    text = text.replace("\xa0", " ")
    # Replace multiple newlines with a single newline
    text = re.sub(r"\n+", "\n", text)
    # Trim leading/trailing spaces
    text = "\n".join(line.strip() for line in text.splitlines())
    return text


def extract_keywords(text: str) -> List[str]:
    """
    Extract keywords from the given text, excluding common English words.

    Args:
        text (str): The text to extract keywords from.

    Returns:
        List[str]: A list of unique keywords sorted alphabetically.
    """
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


def extract_job_info(url: str) -> Dict:
    """
    Extract job information from the given URL. If only partial information
    can be extracted (e.g., company name and job title), still save the URL to
    prevent duplicate processing.

    Args:
        url (str): The URL of the job posting.

    Returns:
        Dict: A dictionary containing the job information. If full extraction
              fails, returns at least the company name, job title, and URL.
    """
    job_info = {
        "job_title": None,
        "company_name": None,
        "location": None,
        "description": None,
        "url": normalize_url(url),
    }

    try:
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            full_title = soup.title.string.strip() if soup.title else None

            # Try to extract company name and job title from page title
            if full_title:
                if "greenhouse" in url:
                    # Greenhouse pattern:
                    # "Job Application for [Job Title] at [Company Name]"
                    match = re.match(
                        r"Job Application for (.+) at (.+)", full_title
                    )
                    if match:
                        job_info["job_title"] = match.group(1).strip()
                        job_info["company_name"] = match.group(2).strip()

                elif "lever" in url:
                    # Lever pattern: "[Company Name] - [Job Title]"
                    parts = full_title.split(" - ", 1)
                    if len(parts) == 2:
                        job_info["company_name"] = parts[0].strip()
                        job_info["job_title"] = parts[1].strip()

            # Greenhouse job board
            if "greenhouse" in url:
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
                    logging.warning(
                        f"  Initial extraction failed. Trying fallback for {url}"
                    )

                    # Fallback to extract location
                    location_div = soup.find("div", class_="location")
                    if location_div:
                        job_info["location"] = location_div.text.strip()
                    else:
                        logging.error(f"  Failed to extract location from {url}")
                        if (
                            not job_info["company_name"]
                            or not job_info["job_title"]
                        ):
                            return None
                        return job_info

                    # Fallback to extract job description
                    job_description_div = soup.find("div", id="content")
                    if job_description_div:
                        raw_text = job_description_div.get_text(separator="\n")
                        job_info["description"] = clean_text(raw_text)
                    else:
                        logging.error(
                            f"  Failed to extract job description from {url}"
                        )
                        return job_info

            # Lever job board
            elif "lever" in url:
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
            logging.error(
                f"  Failed to retrieve page {url}: {response.status_code}"
            )
            return job_info
    except requests.exceptions.RequestException as e:
        logging.error(f"  HTTP request failed: {e}")
        return None


def score_job(title: str, description: str) -> Tuple[int, List[str]]:
    """
    Score the job based on the title, description, and user preferences.

    Args:
        title (str): The job title.
        description (str): The job description.

    Returns:
        Tuple[int, List[str]]: A tuple containing the score and a list of
                               preference hits.
    """
    score = 0
    preference_hits = []
    title, description = title.lower(), description.lower()

    # Add or subtract points based on preferences
    for keyword, value in preferences.items():
        # Match whole words only, e.g. Java in "JavaScript" should not match
        pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
        if pattern.search(title) or pattern.search(description):
            preference_hits.append(keyword)
            score += value

    return score, preference_hits


def extract_salary(description: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract the salary range from the given job description.

    Args:
        description (str): The job description text.

    Returns:
        Tuple[Optional[int], Optional[int]]: A tuple containing the minimum
        and maximum salary values, or (None, None) if no salary is found.
    """
    # Regex to find salary-related phrases with amounts
    salary_pattern = re.compile(
        r"(?i)(?:salary|range)[^$]*\$\s?(\d{1,3}(?:,\d{3})*)"
        r"[^$]*?\$\s?(\d{1,3}(?:,\d{3})*)"
    )
    single_salary_pattern = re.compile(
        r"(?i)(?:salary|range)[^$]*\$\s?(\d{1,3}(?:,\d{3})*)"
    )

    # Try to find a salary range first (two values)
    range_match = salary_pattern.search(description)
    if range_match:
        min_salary = int(range_match.group(1).replace(",", ""))
        max_salary = int(range_match.group(2).replace(",", ""))
        return min_salary, max_salary

    # If no range found, look for a single salary
    single_match = single_salary_pattern.search(description)
    if single_match:
        min_salary = int(single_match.group(1).replace(",", ""))
        return min_salary, None

    return None, None


def save_glassdoor_data_to_csv(company_name: str, glassdoor_data: Dict):
    """
    Save the Glassdoor data for the given company to a CSV file.

    Args:
        company_name (str): The name of the company.
        glassdoor_data (Dict): A dictionary containing the Glassdoor data.

    Returns:
        None
    """
    fieldnames = [
        "company_name",
        "rating",
        "glassdoor_url",
        "reviews",
        "company_size",
    ]
    file_exists = os.path.isfile("glassdoor_data.csv")

    with open("glassdoor_data.csv", mode="a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "company_name": company_name,
                "rating": glassdoor_data.get("rating", "N/A"),
                "glassdoor_url": glassdoor_data.get("glassdoor_url", "unknown"),
                "reviews": glassdoor_data.get("reviews", "N/A"),
                "company_size": glassdoor_data.get("company_size", "unknown"),
            }
        )


def get_glassdoor_data(company_name: str) -> Optional[Dict]:
    """
    Retrieve Glassdoor data for the given company name from the CSV file.

    Args:
        company_name (str): The name of the company to search for.

    Returns:
        Optional[Dict]: A dictionary containing the Glassdoor data, or None if
                        the company is not found in the CSV file.
    """
    try:
        with open("glassdoor_data.csv", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row["company_name"].lower() == company_name.lower():
                    return row
    except FileNotFoundError:
        logging.error("Glassdoor data CSV file not found.")
    return None


def parse_company_size(company_size_text):
    """
    Parse the company size text into a standardized format.

    Args:
        company_size_text (str): The company size text to parse.

    Returns:
        str: The parsed company size in the format "min-max" or "unknown".

    """
    try:
        # Regex to match "51 to 200 Employees", "1K to 5K Employees", etc.
        match = re.match(
            r"(\d+)([K]?)\s*to\s*(\d+)([K]?) Employees", company_size_text
        )
        if match:
            start, start_suffix, end, end_suffix = match.groups()
            start = int(start) * 1000 if start_suffix == "K" else int(start)
            end = int(end) * 1000 if end_suffix == "K" else int(end)
            return f"{start}-{end}"
        elif "Employees" in company_size_text and "+" in company_size_text:
            # Handle cases like "10000+ Employees"
            return company_size_text.replace(" Employees", "").replace("K", "000")
        else:
            return company_size_text  # Return as-is if format is unexpected
    except Exception:
        return "unknown"


def scrape_glassdoor_data(company_name: str) -> Dict:
    """
    Scrape Glassdoor data for the given company name.

    Args:
        company_name (str): The name of the company to search for.

    Returns:
        Dict: A dictionary containing the Glassdoor data.

    """
    # Set up Chrome options to run headless
    options = Options()
    # options.add_argument("--headless")  # Uncomment to run headless
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("user-agent=Mozilla/5.0")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )

    try:
        search_url = (
            "https://www.glassdoor.com/Search/results.htm?"
            f"keyword={company_name.replace(' ', '%20')}"
        )
        driver.get(search_url)
        time.sleep(2)

        rating = "N/A"
        reviews = "N/A"
        company_size = "unknown"
        glassdoor_url = "unknown"

        try:
            # FIRST: Try old layout
            try:
                first_tile = driver.find_element(By.CLASS_NAME, "company-tile")

                # Rating
                try:
                    rating = (
                        first_tile.find_element(
                            By.CSS_SELECTOR, "strong.small.css-b63kyi"
                        )
                        .text.strip()
                        .replace(" ★", "")
                    )
                except Exception:
                    logging.warning(
                        "  No glassdoor rating found in old layout for "
                        f"{company_name}"
                    )

                # Reviews
                try:
                    reviews_span = first_tile.find_elements(
                        By.XPATH, ".//span[contains(text(),'Reviews')]"
                    )[0]
                    reviews = reviews_span.find_element(
                        By.XPATH, "./preceding-sibling::span"
                    ).text.strip()

                    # Might say 1K or 2K, convert to 1000 or 2000
                    if "K" in reviews:
                        reviews = reviews.replace("K", "000")
                except Exception:
                    logging.warning(
                        "  No glassdoor reviews found in old layout for "
                        f"{company_name}"
                    )

                # Size
                try:
                    company_size_text = first_tile.find_element(
                        By.XPATH, ".//span[contains(text(),'Employees')]"
                    ).text.strip()
                    company_size = parse_company_size(company_size_text)
                except Exception:
                    logging.warning(
                        "  No company size found in old layout for "
                        f"{company_name}"
                    )

                # URL
                try:
                    glassdoor_url = first_tile.get_attribute("href")
                except Exception:
                    logging.warning(
                        "  No glassdoor URL found in old layout for "
                        f"{company_name}"
                    )

            except Exception:
                # OLD layout not found — try fallback: NEW layout (company-card)
                try:
                    cards = driver.find_elements(
                        By.CSS_SELECTOR, "div[data-test='company-card']"
                    )
                    for card in cards:
                        try:
                            name_el = card.find_element(
                                By.CLASS_NAME, "employer-card_employerName__YXH4h"
                            )
                            if (
                                company_name.lower()
                                not in name_el.text.strip().lower()
                            ):
                                continue

                            # Rating
                            try:
                                rating = (
                                    card.find_element(
                                        By.CLASS_NAME,
                                        "employer-card_employerRatingContainer__2pK6W",  # noqa
                                    )
                                    .text.split("★")[0]
                                    .strip()
                                )
                            except Exception:
                                logging.warning(
                                    "No rating found in new layout for "
                                    f"{company_name}"
                                )

                            # Reviews
                            try:
                                reviews_span = card.find_elements(
                                    By.XPATH,
                                    ".//span[contains(text(), 'reviews')]/preceding-sibling::span",  # noqa
                                )
                                if reviews_span:
                                    reviews = (
                                        reviews_span[0]
                                        .text.strip()
                                        .replace("K", "000")
                                    )
                            except Exception:
                                logging.warning(
                                    "No reviews found in new layout for "
                                    f"{company_name}"
                                )

                            # URL
                            try:
                                href = card.find_element(
                                    By.TAG_NAME, "a"
                                ).get_attribute("href")
                                glassdoor_url = (
                                    f"https://www.glassdoor.com{href}"
                                    if href.startswith("/")
                                    else href
                                )
                            except Exception:
                                logging.warning(
                                    "No URL found in new layout for "
                                    f"{company_name}"
                                )

                            break  # done if match found

                        except Exception:
                            continue

                except Exception:
                    return {"error": f"No company data found for {company_name}"}

        except Exception:
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


def load_existing_urls(file_name: str = "job_results.csv") -> set:
    """
    Load existing job URLs from the CSV file into a set for fast lookup.

    Args:
        file_name (str): The name of the CSV file to load.

    Returns:
        set: A set containing URLs already present in the CSV.
    """
    urls = set()
    if os.path.isfile(file_name):
        with open(file_name, newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                urls.add(row["url"])
    else:
        logging.info("CSV file not found; starting with an empty URL set.")
    return urls


def save_to_csv(job_info: Dict, file_name: str = "job_results.csv"):
    """
    Save the job information to a CSV file.

    Args:
        job_info (Dict): A dictionary containing the job information.
        file_name (str): The name of the CSV file to save to.

    Returns:
        None
    """
    fieldnames = [
        "company_name",
        "job_title",
        "their_thing",
        "date_first_seen",
        "app_deadline",
        "salary_min",
        "salary_max",
        "location",
        "url",
        "rating",
        "reviews",
        "company_size",
        "glassdoor_url",
        "found_by",
        "score",
        "preference_hits",
        "keywords",
    ]
    file_exists = os.path.isfile(file_name)

    job_info["date_first_seen"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # Filter out any keys that are not part of 'fieldnames'
    filtered_job_info = {key: job_info.get(key, "") for key in fieldnames}

    with open(file_name, mode="a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(filtered_job_info)


if __name__ == "__main__":
    """
    Main entry point of the script.
    """
    # Google search query to find job postings
    # intitle: restricts results to those with specific words in the job title
    # (keyword OR keyword): searches for any of the keywords in the job listing
    # site: restricts results to a specific site, currently Lever and Greenhouse
    # -intitle: excludes results with specific words in the job title
    # "Remote": the word "Remote" must be found anywhere in the job listing
    query = (
        "(intitle:engineer OR intitle:software OR intitle:python OR "
        "intitle:developer OR intitle:data) "
        '(python OR backend OR ml OR "machine learning") '
        # "site:lever.co OR site:greenhouse.io "
        "-intitle:staff -intitle:senior -intitle:manager -intitle:lead "
        "-intitle:principal -intitle:director "
        '"Remote"'
    )

    results = google_search(query)
    logging.info(f"Found {len(results)} job postings.")

    existing_urls = load_existing_urls()

    for i, url in enumerate(results, 1):
        url = normalize_url(url)
        logging.info(f"Processing job {i}/{len(results)}: {url}")

        if url in existing_urls:
            logging.info(f"  Skipping duplicate job: {url}.")
            continue
        job_info = extract_job_info(url)
        if not job_info or not job_info.get("company_name"):
            logging.info("  Skipping job with no information retrieved.")
            continue

        glassdoor_data = get_glassdoor_data(job_info.get("company_name", ""))
        if glassdoor_data:
            logging.info(
                f"  Glassdoor data found for {job_info.get('company_name')}"
            )
            job_info.update(glassdoor_data)
        else:
            glassdoor_data = scrape_glassdoor_data(job_info.get("company_name"))
            save_glassdoor_data_to_csv(
                job_info.get("company_name"), glassdoor_data
            )
            job_info.update(glassdoor_data)

        # If no location, save to csv and continue
        if not job_info.get("location"):
            save_to_csv(job_info, "job_results.csv")
            logging.info("  No location found. Job saved to CSV.")
            continue

        if not in_usa(job_info.get("location", "")):
            logging.info("  Skipping job outside the USA or missing info.")
            logging.info(f"  Location: {job_info.get('location', '')}")
            logging.info(f"  Title: {job_info.get('job_title', '')}")
            continue

        # If no description, save to csv and continue
        if not job_info.get("description"):
            save_to_csv(job_info, "job_results.csv")
            logging.info("  No description found. Job saved to CSV.")
            continue

        job_info["score"], job_info["preference_hits"] = score_job(
            job_info.get("job_title", ""), job_info.get("description", "")
        )

        job_info["salary_min"], job_info["salary_max"] = extract_salary(
            job_info.get("description", "")
        )
        job_info["keywords"] = extract_keywords(job_info.get("description", ""))

        # Blank placeholders for their_thing and app_deadline
        job_info["their_thing"] = ""
        job_info["app_deadline"] = ""
        job_info["found_by"] = "job-scraper"

        save_to_csv(job_info)
        logging.info(f"  Job added to the CSV file: {job_info.get('job_title')}")

    logging.info("All jobs processed.")
