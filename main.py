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
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from locations import allow_locales, states_and_cities, exclude_locales


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
    Perform a Google search and return the list of result URLs.

    Args:
        query (str): The search query to perform.
        num (int): The number of results to return (default 3).

    Returns:
        List[str]: A list of URLs from the search results.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    }
    search_url = f"https://www.google.com/search?q={query}&num={num_results}"
    response = requests.get(search_url, headers=headers)

    if response.status_code != 200:
        logging.error(
            f"Failed to retrieve Google search results: {response.status_code}"
        )
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    search_results = []

    for g in soup.find_all("div", class_="g"):
        anchor = g.find("a")
        if anchor:
            link = anchor["href"]
            search_results.append(normalize_url(link))

    return search_results


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
    return urlunparse(normalized)


def in_usa(location: str) -> bool:
    """
    Check if the given location is in the USA.

    Args:
        location (str): The location string.

    Returns:
        bool: True if the location is in the USA, False otherwise
    """
    location = location.lower()

    delimiters = [",", "/", "-", "(", ")", " "]  # Split by space or no?
    pattern = "|".join(map(re.escape, delimiters))
    words = re.split(pattern, location)

    # Check if any part of the location matches an exclude keyword
    for word in words:
        if word.strip() in exclude_locales:
            return False

    # Check if any part of the location matches an allow keyword or US city/state
    for word in words:
        if word.strip() in allow_locales or word.strip() in states_and_cities:
            return True

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
                "rating": glassdoor_data["rating"],
                "glassdoor_url": glassdoor_data["glassdoor_url"],
                "reviews": glassdoor_data["reviews"],
                "company_size": glassdoor_data["company_size"],
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


def scrape_glassdoor_data(company_name: str) -> Dict:
    """
    Scrape Glassdoor data for the given company name.

    Args:
        company_name (str): The name of the company to search for.

    Returns:
        Dict: A dictionary containing the Glassdoor data.

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
            except Exception:
                glassdoor_url = "N/A"

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


def job_exists_in_csv(url: str) -> bool:
    """
    Check if the job already exists in the CSV file.

    Args:
        url (str): The URL of the job posting.

    Returns:
        bool: True if the job already exists, False otherwise.
    """
    # Check if the file exists
    if not os.path.isfile("job_results.csv"):
        return False

    with open("job_results.csv", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            if row["url"] == url:
                logging.info(f"  Duplicate job found: {url}. Skipping.")
                return True
    return False


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
        "date_first_seen",
        "salary_min",
        "salary_max",
        "location",
        "url",
        "rating",
        "glassdoor_url",
        "reviews",
        "company_size",
        "score",
        "preference_hits",
        "keywords",
    ]
    file_exists = os.path.isfile(file_name)

    job_info.pop("description", None)
    job_info["date_first_seen"] = time.strftime("%Y-%m-%d %H:%M:%S")

    with open(file_name, mode="a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(job_info)


if __name__ == "__main__":
    """
    Main entry point of the script.
    """
    query = (
        "(intitle:engineer OR intitle:software OR intitle:python OR "
        "intitle:developer OR intitle:data) "
        '(python OR backend OR ml OR "machine learning") '
        "site:lever.co OR site:greenhouse.io "
        "-intitle:staff -intitle:senior -intitle:manager -intitle:lead "
        '-intitle:principal -intitle:director "Remote"'
    )

    results = google_search(query, 10)

    for url in results:
        url = normalize_url(url)
        logging.info(f"Processing URL: {url}")
        # If job url already exists in the CSV file, skip it
        if job_exists_in_csv(url):
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
            logging.info(
                f"  No Glassdoor data found for {job_info.get('company_name')}"
            )
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

        save_to_csv(job_info)
        logging.info(f"  Job added to the CSV file: {job_info.get('job_title')}")

    logging.info("All jobs processed.")
