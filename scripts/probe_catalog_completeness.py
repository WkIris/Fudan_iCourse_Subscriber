import contextlib
import io
import json
import math
import time
from collections import Counter

from src.api.icourse import ICourseClient
from src.api.webvpn import SecondFactorError, WebVPNSession


def login():
    for attempt in range(5):
        session = WebVPNSession()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                session.login()
                session.authenticate_icourse()
            return ICourseClient(session)
        except SecondFactorError:
            session.session.close()
            raise
        except Exception as error:
            session.session.close()
            print(f"Login attempt {attempt + 1}: {type(error).__name__}")
            if attempt == 4:
                raise RuntimeError("Unable to open iCourse session") from None
            time.sleep(5)


def scan(client, term, per_page):
    first = client.get_course_list(term=term, per_page=per_page)
    pages = [first]
    for page in range(2, math.ceil(first["total"] / per_page) + 1):
        pages.append(client.get_course_list(term=term, page=page, per_page=per_page))

    ids = Counter()
    records = Counter()
    pages_by_id = Counter()
    missing_ids = 0
    for page in pages:
        ids_on_page = set()
        for row in page["courses"]:
            cid = row.get("id") or row.get("course_id")
            if cid:
                ids[str(cid)] += 1
                ids_on_page.add(str(cid))
            else:
                missing_ids += 1
            records[json.dumps(row, sort_keys=True, ensure_ascii=False)] += 1
        pages_by_id.update(ids_on_page)

    print(json.dumps({
        "term": term,
        "page_size": per_page,
        "announced_totals": sorted({page["total"] for page in pages}),
        "page_lengths": [len(page["courses"]) for page in pages],
        "unique_course_ids": len(ids),
        "missing_ids": missing_ids,
        "duplicate_id_rows": ids.total() - len(ids),
        "duplicate_full_rows": records.total() - len(records),
        "ids_on_multiple_pages": sum(count > 1 for count in pages_by_id.values()),
    }), flush=True)
    return set(ids), set(records)


def main():
    client = login()
    targets = {"2025-20262", "2025-20261", "2024-20251", "2023-2024-2"}
    try:
        for term in client.discover_terms():
            if term["name"] not in targets:
                continue
            announced = term["count"]
            try:
                ids_a, rows_a = scan(client, term["code"], 500)
                ids_b, rows_b = scan(client, term["code"], 400)
                print(json.dumps({
                    "term": term["code"],
                    "discovered_total": announced,
                    "id_union": len(ids_a | ids_b),
                    "row_union": len(rows_a | rows_b),
                    "new_ids_on_second_scan": len(ids_b - ids_a),
                }), flush=True)
            except Exception as error:
                print(f"Term {term['code']} could not finish: {type(error).__name__}")
    finally:
        client.vpn.session.close()


if __name__ == "__main__":
    main()
