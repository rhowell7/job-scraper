# Job Scraper

Job Scraper is a Python-based application designed to scrape job listings from
Greenhouse.io and Lever.co and aggregate them into a single, searchable database.

## Features

- Scrape job listings from Greenhouse.io and Lever.co
- Store job listings in a database
- Search and filter job listings by keywords, preferences, and more
- Export job listings to CSV in `result/` directory

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/rhowell7/job-scraper.git
    ```
2. Navigate to the project directory:
    ```sh
    cd job-scraper
    ```
3. Create and activate a virtual environment:
    ```sh
    python -m venv venv
    source venv/bin/activate  # `deactivate` when finished
    ```
4. Install the required dependencies:
    ```sh
    pip install -r requirements.txt
    ```

## Local Usage

### Custom Search API
To run locally, first create a [Programmable Google Search Engine](https://programmablesearchengine.google.com/about/).

Enable the Custom Search API:
https://console.cloud.google.com/apis/library/customsearch.googleapis.com
APIs & Services > Library > Search for Custom Search API
Credentials > create an API Key

Create a `.env` file in the root directory with the following variables:
```
API_KEY=<your_google_api_key>
SEARCH_ENGINE_ID=<your_google_search_engine_id>
```

### Local PostgresQL Database

Install [PostgresQL](https://www.postgresql.org/download/).
Start and enable the PostgresQL service:
```sh
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

By default, PostgreSQL stores its data in the `/var/lib/postgresql/` directory. Create a database and user:
```sh
sudo -u postgres psql
postgres=# CREATE DATABASE job_scraper;
postgres=# CREATE USER <db_user> WITH PASSWORD '<db_pass>';
postgres=# GRANT ALL PRIVILEGES ON DATABASE job_scraper TO <db_user>;
postgres=# \q
```

Add the new variables to the `.env` file:
```
API_KEY=<your_google_api_key>
SEARCH_ENGINE_ID=<your_google_search_engine_id>
DB_HOST=localhost
DB_NAME=job_scraper
DB_USER=<db_user>
DB_PASS=<db_pass>
```

### Run the Application

Run the application:
```sh
python main.py
```

### View the results

The script should create three tables in the database: `jobs`, `foreign_jobs`, and `glassdoor_data`.
You can view the results by connecting to the database:
```sh
sudo -u postgres psql
postgres=# \c job_scraper
job_scraper=# SELECT * FROM jobs;
job_scraper=# SELECT * FROM foreign_jobs;
job_scraper=# SELECT * FROM glassdoor_data;
```

## Testing

To run the tests, install `tox`:
```sh
pip install tox
```

Run the tests:
```sh
tox
```

Or, run the tests one by one after activating the virtual environment:
```sh
source venv/bin/activate
pytest
flake8 --exclude .tox,.git,venv/ .
black --check .
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
Please make sure `tox` passes before submitting a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
