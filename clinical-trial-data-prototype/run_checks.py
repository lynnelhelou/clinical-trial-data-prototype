"""
Runs every validation query in checks.sql, saves the flagged records,
compares the results with answer_key.csv, and builds a per-site report.

Run:  python run_checks.py     (after generate_data.py)
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path("clinical_trial.db")
OUT_DIR = Path("output")


def load_sql_sections(path):
    text = path.read_text()
    parts = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def main():
    OUT_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)

    # 1. Run all checks
    frames = []
    for name, sql in load_sql_sections(Path("checks.sql")).items():
        frames.append(pd.read_sql_query(sql, con))
    issues = pd.concat(frames, ignore_index=True)
    issues.to_csv(OUT_DIR / "all_flagged_issues.csv", index=False)

    # 2. Compare with the answer key
    key = pd.read_csv("answer_key.csv")
    seeded = key.groupby("error_type").size()
    found = issues.groupby("check_name").size()
    comparison = pd.DataFrame({"seeded": seeded, "found": found}).fillna(0).astype(int)
    comparison["match"] = comparison["seeded"] == comparison["found"]
    comparison.loc["TOTAL"] = [comparison["seeded"].sum(), comparison["found"].sum(),
                               comparison["seeded"].sum() == comparison["found"].sum()]
    comparison.to_csv(OUT_DIR / "check_vs_answer_key.csv")
    print("\nDid the checks find every planted error?\n")
    print(comparison.to_string())

    # Also confirm they are the SAME records, not just the same counts
    def record_id(row):
        if row.check_name in ("duplicate_participant", "status_mismatch"):
            return str(row.participant_id)
        return str(int(row.visit_id))

    key_records = set(zip(key["error_type"], key["record"].astype(str)))
    found_records = {(r.check_name, record_id(r)) for r in issues.itertuples(index=False)}
    print(f"\nExact record match: {key_records == found_records}")

    # 3. Site monitoring report
    visits_per_site = pd.read_sql_query(
        """SELECT p.site_id, COUNT(*) AS completed_visits
           FROM visits v JOIN participants p ON p.participant_id = v.participant_id
           WHERE v.status = 'Completed' GROUP BY p.site_id""", con).set_index("site_id")
    site = issues.groupby("site_id").size().rename("issues").to_frame()
    site = site.join(visits_per_site)
    site["issues_per_100_visits"] = (100 * site["issues"] / site["completed_visits"]).round(1)
    site = site.sort_values("issues_per_100_visits", ascending=False)
    site.to_csv(OUT_DIR / "site_report.csv")
    print("\nSite report (worst first):\n")
    print(site.to_string())
    con.close()


if __name__ == "__main__":
    main()
