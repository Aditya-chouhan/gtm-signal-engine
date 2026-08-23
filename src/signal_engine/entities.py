"""Canonical entity list for this artifact.

Every entity here is a real public company, chosen for one reason only:
verifiable coverage across all three signal sources (a GitHub org that
actually exists, a ticker/CIK that actually files with the SEC, a name
worth searching on Hacker News). That is the *only* selection criterion.

This is NOT a real prospect/target account list. These are large public
SaaS companies, not realistic outbound targets for a solo GTM consulting
practice -- using them as a real sales list would misrepresent who this
engine would actually be pointed at in production. They exist here purely
so the multi-source fusion mechanism can be proven against real, live,
independently-checkable data instead of invented company records.

CIKs were pulled from SEC's own https://www.sec.gov/files/company_tickers.json
on 2026-08-23 (see scripts/refresh_entities.py) -- not typed from memory.
GitHub orgs were confirmed live via `GET /orgs/{org}` returning 200 the same
day (see build log in README). One planned entity, Confluent (CFLT), was
dropped: it does not appear in SEC's own ticker file (data as of 2026-08-23;
possibly a coverage gap in that file, not evidence Confluent doesn't file --
not worth chasing down for a 15th data point when 14 already gives full
source coverage).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    name: str
    ticker: str
    cik: str  # zero-padded 10-digit, as SEC's EDGAR API requires
    github_org: str
    hn_aliases: tuple  # exact strings this entity is searched for on HN


ENTITIES = [
    Entity("Salesforce", "CRM", "0001108524", "salesforce", ("Salesforce",)),
    Entity("HubSpot", "HUBS", "0001404655", "HubSpot", ("HubSpot",)),
    Entity("Snowflake", "SNOW", "0001640147", "snowflakedb", ("Snowflake",)),
    Entity("MongoDB", "MDB", "0001441816", "mongodb", ("MongoDB",)),
    Entity("Datadog", "DDOG", "0001561550", "DataDog", ("Datadog",)),
    Entity("Elastic", "ESTC", "0001707753", "elastic", ("Elastic", "Elasticsearch")),
    Entity("GitLab", "GTLB", "0001653482", "gitlab-org", ("GitLab",)),
    Entity("Twilio", "TWLO", "0001447669", "twilio", ("Twilio",)),
    Entity("Asana", "ASAN", "0001477720", "Asana", ("Asana",)),
    Entity("monday.com", "MNDY", "0001845338", "mondaycom", ("monday.com",)),
    Entity("Zscaler", "ZS", "0001713683", "zscaler", ("Zscaler",)),
    Entity("Okta", "OKTA", "0001660134", "okta", ("Okta",)),
    Entity("CrowdStrike", "CRWD", "0001535527", "CrowdStrike", ("CrowdStrike",)),
    Entity("Cloudflare", "NET", "0001477333", "cloudflare", ("Cloudflare",)),
]

BY_TICKER = {e.ticker: e for e in ENTITIES}
