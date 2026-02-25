# ======================================================================
# SCRAPER TEMPLATE
#
# Nutzung:
#   1. Datei kopieren und nach <company>_<mode>.py umbenennen.
#   2. Alle mit "# TODO:" markierten Stellen ausfüllen.
#   3. RESPONSE_TYPE auf "json" oder "html" setzen und die passende
#      JOB_DATA_KEYS-Variante einkommentieren.
#   4. Extractor-Modul in scraping/extract/ anlegen und Import anpassen.
# ======================================================================

import logging
import re
import sys
import os
import time
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Templates.schemas.detailjob.builder import build_detailjob

# TODO: Extractor-Modul für diese Company anlegen und Import anpassen.
#       Vorlage: scraping/extract/extractor_base.py
from Templates.extractors.company_detail_extractor import extract_detail_sections

from Templates.db_runs import (
    start_run,
    finish_run,
    update_stage,
    get_conn,
    upsert_job_and_payload_from_master,
    touch_jobs_last_seen,
    mark_jobs_inactive,
)
from Templates.util_v5 import (
    fetch_url,
    load_master_list,
    save_master_list,
    get_current_date,
    update_job_status,
    get_nested_value,           # wird nur im JSON-Modus verwendet
    upload_detailjob_json_to_gcs,
)
from Templates.RunMetrics import _update_http_columns_in_db
from Templates.DBNormalize import _prepare_job_for_db, _now_utc_iso

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# ======================================================================
# KONFIGURATION – alle TODO-Stellen ausfüllen
# ======================================================================

# TODO: Company-Bezeichner (werden als GCS-Ordner, DB-Key und Logging-Label genutzt)
BUCKET_NAME = "TODO_bucket_name"
FOLDER_NAME = "TODO_company"
COMPANY_KEY = "TODO_company"

# TODO: "json" wenn die API JSON liefert, "html" bei HTML-Seiten
RESPONSE_TYPE = "json"          # "json" | "html"

# TODO: Proxy-Nutzung nach Bedarf aktivieren
USE_PROXY_DAILY_LIST        = False
USE_PROXY_DETAILED_POSTINGS = False

# TODO: True, wenn die API mehrere Seiten liefert
USE_PAGINATION = False

# TODO: HTTP-Methode für Listen- und Einzeljob-Requests
REQUEST_TYPE_LIST   = "get"     # "get" | "post"
REQUEST_TYPE_SINGLE = "get"     # "get" | "post"

MAX_JOBS_PER_PAGE = 100         # TODO: an das API-Limit anpassen
PAGE_START        = 0           # TODO: 0 oder 1, je nach API

# Paginierungsstrategie (nur relevant wenn USE_PAGINATION = True):
#   "page"      -> params[KEY_NAME] = aktuelle Seitennummer
#   "offset"    -> params[KEY_NAME] = page * MAX_JOBS_PER_PAGE
#   "firstItem" -> params[KEY_NAME] = page * MAX_JOBS_PER_PAGE + 1
PAGINATION_MODE = "offset"      # TODO: "page" | "offset" | "firstItem"

# -----------------------------------------------------------------------
# Request-Setup
# -----------------------------------------------------------------------

# TODO: Endpunkt der Joblisten-API
DAILY_JOB_URL = "https://TODO_list_endpoint"

# TODO: Benötigte Request-Header eintragen
HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    # "Authorization": "Bearer TODO_token",
}

# TODO: Query-Parameter für den Listenaufruf
PARAMS: Dict[str, Any] = {
    # "limit": MAX_JOBS_PER_PAGE,
}

JSON_PAYLOAD = None     # TODO: Dict-Payload für POST-Requests, sonst None
DATA        = None      # TODO: Form-Data für POST-Requests, sonst None

# -----------------------------------------------------------------------
# Detail-Request-Setup
# Standardmäßig werden HEADERS/PARAMS vom Listenaufruf wiederverwendet.
# Nur abweichende Werte eintragen – alles was None bleibt, fällt auf den
# Listenwert zurück.
# -----------------------------------------------------------------------

# TODO: Separate Header für Detail-Requests, falls abweichend (sonst None)
HEADERS_SINGLE: Optional[Dict[str, str]] = None
# Beispiel:
# HEADERS_SINGLE = {
#     **HEADERS,
#     "Accept": "application/json",
# }

# TODO: Separate Query-Parameter für Detail-Requests, falls abweichend (sonst None)
PARAMS_SINGLE: Optional[Dict[str, Any]] = None
# Beispiel:
# PARAMS_SINGLE = {"lang": "de", "expand": "description"}

JSON_PAYLOAD_SINGLE = None  # TODO: Dict-Payload für Detail-POST-Requests, sonst None
DATA_SINGLE         = None  # TODO: Form-Data für Detail-POST-Requests, sonst None

# -----------------------------------------------------------------------
# JSON-Modus: Pfade in der API-Antwort
# (nur relevant wenn RESPONSE_TYPE == "json")
# -----------------------------------------------------------------------

KEY_NAME      = "limit"                  # TODO: Param-Name für Paginierung (z.B. "limit", "size")
JOBS_LIST_KEY = ["data", "results"]      # TODO: Pfad zur Job-Liste in der JSON-Antwort
TOTAL_JOBS_KEY = ["data", "total"]       # TODO: Pfad zur Gesamtzahl, oder [] wenn nicht vorhanden

# -----------------------------------------------------------------------
# HTML-Modus: Container-Selektor pro Job-Zeile
# (nur relevant wenn RESPONSE_TYPE == "html")
# -----------------------------------------------------------------------

JOB_LIST_KEY = "div.TODO_job_row"        # TODO: CSS-Selektor, der genau ein Element pro Job trifft

# -----------------------------------------------------------------------
# Feld-Extraktion
#
# JSON-Modus:  Wert = Liste von Nested-Keys  z.B. ["location", "city"]
# HTML-Modus:  Wert = CSS-Selektor-String    z.B. "div.job-title[data-title]"
#
# TODO: Passende Variante einkommentieren und anpassen, andere auskommentieren.
# -----------------------------------------------------------------------

# -- JSON-Variante (RESPONSE_TYPE = "json") --
# JOB_DATA_KEYS: Dict[str, List] = {
#     "id":               ["jobId"],                          # TODO
#     "jobTitle":         ["title"],                          # TODO
#     "location":         ["location", "city"],               # TODO
#     "department":       ["categories", "department"],       # TODO
#     "company":          ["company", "name"],                # TODO
#     "contract":         ["contractType"],                   # TODO
#     "career_level":     ["seniorityLevel"],                 # TODO
#     "employment_type":  ["workType"],                       # TODO
#     "created":          ["postedDate"],                     # TODO
#     "link":             ["applyUrl"],                       # TODO
# }

# -- HTML-Variante (RESPONSE_TYPE = "html") --
JOB_DATA_KEYS: Dict[str, str] = {
    "id":               "div.TODO_id_cell",                   # TODO
    "jobTitle":         "div.TODO_title[data-job-title]",     # TODO
    "location":         "div.TODO_location[data-job-location]", # TODO
    "department":       "div.TODO_dept[data-job-field]",      # TODO
    "company":          "div.TODO_company[data-entity]",      # TODO
    "contract":         "",                                   # TODO oder leer lassen
    "career_level":     "div.TODO_level[data-job-type]",      # TODO
    "employment_type":  "",                                   # TODO oder leer lassen
    "created":          "div.TODO_date[data-posting-date]",   # TODO
    "link":             "a.TODO_apply_link[href]",            # TODO
}

# Optional: Überschreibt, wie der Wert aus dem Element/Value extrahiert wird.
# JSON-Beispiele:  "created": lambda v: v[:10] if v else None
# HTML-Beispiele:  "id":      lambda el: el.get_text(strip=True)
#                  "link":    lambda el: el.get("href")
#                  "created": lambda el: el.get("data-posting-date")
extraction_logic: Dict[str, Any] = {
    # TODO: Extraktions-Lambdas nach Bedarf eintragen
}

# -----------------------------------------------------------------------
# Detail-URL
#
# TODO: Eine der beiden Varianten implementieren, andere auskommentieren.
#
# Option A – URL aus Base-URL + Job-ID konstruieren (z.B. Audi-Stil):
#   BASE_DETAIL_URL = "https://TODO_careers.example.com/jobs/"
#   def _build_detail_url(job_id: str, job: Optional[Dict] = None) -> Optional[str]:
#       return BASE_DETAIL_URL + job_id
#
# Option B – Link steckt bereits im Listing (z.B. BMW-Stil):
#   DETAIL_BASE_HOST = "https://TODO_base.example.com"
#   def _build_detail_url(job_id: str, job: Optional[Dict] = None) -> Optional[str]:
#       link = job.get("link") if job else None
#       if link and link.startswith("/"):
#           link = DETAIL_BASE_HOST + link
#       return link or None
# -----------------------------------------------------------------------

BASE_DETAIL_URL = "https://TODO_careers.example.com/jobs/"  # TODO (Option A)


def _build_detail_url(job_id: str, job: Optional[Dict] = None) -> Optional[str]:
    # TODO: Implementierung nach oben stehender Vorlage einsetzen.
    return BASE_DETAIL_URL + str(job_id)


# ======================================================================
# HTTP-Tracking
# ======================================================================

HTTP_STATS: Optional[Dict] = None


# ======================================================================
# Hilfsfunktionen
# ======================================================================

def _clean_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", t)
    t = t.strip()
    return t or None


def _fallback_fulltext(raw_text: str) -> Optional[str]:
    """Plaintext-Fallback, wenn der Extractor keinen Fulltext liefert."""
    try:
        soup = BeautifulSoup(raw_text, "lxml")
        return _clean_text(soup.get_text(separator="\n"))
    except Exception:
        return None


# ======================================================================
# Kern-Scraping-Logik
# ======================================================================

def process_jobs(job_data: list) -> List[Dict]:
    """
    Normalisiert Rohdaten (JSON-Dicts oder BeautifulSoup-Elemente) zu
    einer Liste einheitlicher Job-Dicts. Verhält sich je nach RESPONSE_TYPE.
    """
    jobs = []
    base_fields: Dict[str, Any] = {
        "scraping_date": None,
        "last_updated":  None,
        "status":        None,
        "keywords":      [],
    }

    for item in job_data:
        job: Dict[str, Any] = {**base_fields}

        if RESPONSE_TYPE == "json":
            for key, path in JOB_DATA_KEYS.items():
                if not path:
                    continue
                value = get_nested_value(item, path)
                extractor = extraction_logic.get(key, lambda x: x)
                job[key] = extractor(value)

        elif RESPONSE_TYPE == "html":
            for key, selector in JOB_DATA_KEYS.items():
                if not selector:
                    continue
                element = item.select_one(selector)
                if not element:
                    continue
                # Attribut-Selektoren wie [data-foo] automatisch erkennen
                attr_match = re.search(r"\[([^\]=]+)\]$", selector)
                if attr_match:
                    attr_name = attr_match.group(1)
                    extractor = extraction_logic.get(key, lambda el, a=attr_name: el.get(a))
                else:
                    extractor = extraction_logic.get(key, lambda el: el.get_text(strip=True))
                job[key] = extractor(element)

        jobs.append(job)

    return jobs


def fetch_job_list_page(page: int):
    """
    Ruft eine Seite der Job-Liste ab und gibt (verarbeitete Jobs, Gesamtzahl) zurück.
    Paginierungsparameter werden automatisch nach PAGINATION_MODE gesetzt.
    """
    params = {**PARAMS}

    if USE_PAGINATION:
        if PAGINATION_MODE == "page":
            params[KEY_NAME] = page
        elif PAGINATION_MODE == "offset":
            params[KEY_NAME] = page * MAX_JOBS_PER_PAGE
        elif PAGINATION_MODE == "firstItem":
            params[KEY_NAME] = page * MAX_JOBS_PER_PAGE + 1

    response = fetch_url(
        DAILY_JOB_URL,
        headers=HEADERS,
        params=params,
        json=JSON_PAYLOAD,
        data=DATA,
        use_proxy=USE_PROXY_DAILY_LIST,
        max_retries=3,
        timeout=10,
        request_type=REQUEST_TYPE_LIST,
        http_stats=HTTP_STATS,
    )

    if not response:
        logging.error("Job-Liste konnte nach mehreren Versuchen nicht abgerufen werden.")
        return [], 0

    if RESPONSE_TYPE == "json":
        try:
            raw = response.json()
        except ValueError as e:
            logging.error(f"JSON-Parsing fehlgeschlagen: {e}")
            return [], 0

        total = get_nested_value(raw, TOTAL_JOBS_KEY) or 0 if page == PAGE_START else 0
        raw_list = get_nested_value(raw, JOBS_LIST_KEY)
        if not isinstance(raw_list, list):
            logging.error("Unerwartete JSON-Struktur: Job-Liste nicht unter JOBS_LIST_KEY gefunden.")
            return [], total
        return process_jobs(raw_list), total

    elif RESPONSE_TYPE == "html":
        try:
            soup = BeautifulSoup(response.text, "html.parser")
            elements = soup.select(JOB_LIST_KEY)
        except Exception as e:
            logging.error(f"HTML-Parsing fehlgeschlagen: {e}")
            return [], 0
        return process_jobs(elements), 0

    return [], 0


def fetch_all_jobs() -> List[Dict]:
    """
    Ruft alle Job-Listings ab (paginiert oder als Einzelaufruf).
    Gibt verarbeitete Job-Dicts zurück.
    """
    all_jobs: List[Dict] = []

    if USE_PAGINATION:
        page = PAGE_START
        total_from_api = 0
        while True:
            logging.info(f"Abruf Seite {page} ...")
            jobs, total = fetch_job_list_page(page)
            if not jobs:
                break
            if page == PAGE_START and total:
                total_from_api = total
            all_jobs.extend(jobs)
            if total_from_api and len(all_jobs) >= total_from_api:
                break
            if len(jobs) < MAX_JOBS_PER_PAGE:
                break
            page += 1
    else:
        logging.info("Einzelseitiger Abruf der Job-Listings ...")
        jobs, _ = fetch_job_list_page(PAGE_START)
        if jobs:
            all_jobs.extend(jobs)
        else:
            logging.info("Keine Job-Listings gefunden.")

    return all_jobs


def update_master_list_with_jobs(
    all_jobs: List[Dict],
    master_list: list,
):
    current_date = get_current_date()

    new_jobs_count      = 0
    inactive_jobs_count = 0
    skipped_jobs_count  = 0
    db_jobs_written     = 0
    db_jobs_failed      = 0

    seen_job_ids: List[str] = []

    for job in all_jobs:
        job_id = job.get("id")
        if not job_id:
            skipped_jobs_count += 1
            continue

        job_id_str = str(job_id)
        seen_job_ids.append(job_id_str)

        existing = next(
            (e for e in master_list if str(e.get("id")) == job_id_str), None
        )

        if existing:
            update_job_status(existing, current_date)
        else:
            job["scraping_date"] = current_date
            job["last_updated"]  = current_date
            job["status"]        = "active"
            master_list.append(job)
            new_jobs_count += 1

            # Phase-1-DB-Ingest: nur neue Jobs
            try:
                db_job = _prepare_job_for_db(job)
                upsert_job_and_payload_from_master(FOLDER_NAME, db_job)
                db_jobs_written += 1
            except Exception as _db_e:
                db_jobs_failed += 1
                logging.exception(
                    f"DB-Ingest fehlgeschlagen für {FOLDER_NAME} job_id={job_id_str}: {_db_e}"
                )

            # Detail-Fetch und Upload (nur für neue Jobs)
            detail_url = _build_detail_url(job_id_str, job)
            if detail_url:
                response = fetch_url(
                    detail_url,
                    headers=HEADERS_SINGLE if HEADERS_SINGLE is not None else HEADERS,
                    params=PARAMS_SINGLE,
                    json=JSON_PAYLOAD_SINGLE,
                    data=DATA_SINGLE,
                    use_proxy=USE_PROXY_DETAILED_POSTINGS,
                    max_retries=3,
                    timeout=10,
                    request_type=REQUEST_TYPE_SINGLE,
                    http_stats=HTTP_STATS,
                )
                if response:
                    detail_model = build_detailjob(
                        version="0.1",
                        job_id=job_id_str,
                        metadata={
                            "company_key": FOLDER_NAME,
                            "url":         detail_url,
                            "scraped_at":  _now_utc_iso(),
                            "locale":      "de_DE",  # TODO: Locale anpassen
                        },
                        job_meta={
                            "title":           job.get("jobTitle"),
                            "location_text":   job.get("location"),
                            "employment_type": job.get("employment_type"),
                            "contract_type":   job.get("contract"),
                            "career_level":    job.get("career_level"),
                        },
                    )

                    # TODO: input_type ggf. auf "xml" ändern, wenn der Detail-Response XML ist
                    sections = extract_detail_sections(
                        raw=response.text, input_type=RESPONSE_TYPE
                    )

                    fulltext = sections.get("fulltext") or _fallback_fulltext(response.text)
                    detail_model.extracted.fulltext              = fulltext
                    detail_model.extracted.overview              = sections.get("overview")
                    detail_model.extracted.responsibilities.items = sections.get("responsibilities") or []
                    detail_model.extracted.requirements.items    = sections.get("requirements") or []
                    detail_model.extracted.additional.items      = sections.get("additional") or []
                    detail_model.extracted.benefits.items        = sections.get("benefits") or []
                    detail_model.extracted.process               = sections.get("process")

                    upload_detailjob_json_to_gcs(
                        detail_model.model_dump(),
                        job_id_str,
                        BUCKET_NAME,
                        FOLDER_NAME,
                    )

    # DB: last_seen_at für alle heute gesehenen Jobs aktualisieren
    try:
        touch_jobs_last_seen(FOLDER_NAME, seen_job_ids, current_date)
    except Exception as _e:
        logging.exception(f"DB touch last_seen_at fehlgeschlagen für {FOLDER_NAME}: {_e}")

    # Master-Liste: Jobs als inaktiv markieren, die heute nicht gesehen wurden
    inactive_ids: List[str] = []
    for entry in master_list:
        if entry.get("last_updated") != current_date:
            entry["status"] = "inactive"
            inactive_jobs_count += 1
            if entry.get("id"):
                inactive_ids.append(str(entry["id"]))

    try:
        mark_jobs_inactive(FOLDER_NAME, inactive_ids)
    except Exception as _e:
        logging.exception(f"DB mark inactive fehlgeschlagen für {FOLDER_NAME}: {_e}")

    return new_jobs_count, inactive_jobs_count, skipped_jobs_count, db_jobs_written, db_jobs_failed


# ======================================================================
# Einstiegspunkt
# ======================================================================

def main():
    logging.info(f"Scraper gestartet für {FOLDER_NAME}")

    run_id = start_run(
        company_key=COMPANY_KEY,
        meta={
            "bucket":                      BUCKET_NAME,
            "folder":                      FOLDER_NAME,
            "response_type":               RESPONSE_TYPE,
            "use_proxy_daily_list":        USE_PROXY_DAILY_LIST,
            "use_proxy_detailed_postings": USE_PROXY_DETAILED_POSTINGS,
            "use_pagination":              USE_PAGINATION,
            "pagination_mode":             PAGINATION_MODE if USE_PAGINATION else "single_page",
        },
    )

    global HTTP_STATS
    HTTP_STATS = {}

    start_time = time.time()
    cpu_usage  = None

    try:
        update_stage(run_id, "started")

        if PSUTIL_AVAILABLE:
            try:
                cpu_usage = psutil.cpu_percent(interval=1)
            except Exception:
                cpu_usage = None

        update_stage(run_id, "fetch_list")
        all_jobs = fetch_all_jobs()

        update_stage(run_id, "load_master")
        master_list = load_master_list(BUCKET_NAME, FOLDER_NAME)

        update_stage(run_id, "update_master")
        new_jobs_count, inactive_jobs_count, skipped_jobs_count, db_jobs_written, db_jobs_failed = (
            update_master_list_with_jobs(all_jobs, master_list)
        )

        update_stage(run_id, "save_master")
        save_master_list(BUCKET_NAME, FOLDER_NAME, master_list)

        execution_time = time.time() - start_time

        finish_run(
            run_id=run_id,
            status="success",
            execution_time_sec=execution_time,
            cpu_usage_pct=cpu_usage,
            jobs_fetched=len(all_jobs),
            jobs_processed=len(all_jobs),
            new_jobs=new_jobs_count,
            inactive_jobs=inactive_jobs_count,
            skipped_jobs=skipped_jobs_count,
            meta={
                "http":             HTTP_STATS,
                "db_jobs_written":  db_jobs_written,
                "db_jobs_failed":   db_jobs_failed,
            },
        )

        try:
            _update_http_columns_in_db(run_id, HTTP_STATS, conn_factory=get_conn)
        except Exception as _e:
            logging.warning(f"http_*-Spalten konnten nicht aktualisiert werden für Run {run_id}: {_e}")

        update_stage(run_id, "finished_success")

        logging.info(f"Fertig. {len(all_jobs)} Jobs verarbeitet.")
        logging.info(f"{new_jobs_count} neu | {inactive_jobs_count} inaktiv | {skipped_jobs_count} übersprungen")
        logging.info(f"DB: {db_jobs_written} geschrieben, {db_jobs_failed} fehlgeschlagen")

    except Exception as e:
        execution_time = time.time() - start_time

        update_stage(run_id, "failed", meta={"exception_type": type(e).__name__})

        finish_run(
            run_id=run_id,
            status="failed",
            execution_time_sec=execution_time,
            cpu_usage_pct=cpu_usage,
            jobs_fetched=len(all_jobs) if "all_jobs" in locals() and all_jobs else None,
            jobs_processed=len(all_jobs) if "all_jobs" in locals() and all_jobs else None,
            error_message=str(e),
            meta={
                "exception_type": type(e).__name__,
                "http":           HTTP_STATS,
            },
        )

        try:
            _update_http_columns_in_db(run_id, HTTP_STATS or {}, conn_factory=get_conn)
        except Exception as _e:
            logging.warning(f"http_*-Spalten konnten nicht aktualisiert werden für Run {run_id}: {_e}")

        logging.exception("Scraping fehlgeschlagen.")
        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    main()
