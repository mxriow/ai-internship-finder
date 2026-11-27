"""Provider registry. Each provider exposes:

    feed_url(token, **opts) -> str           human-readable feed URL
    fetch(client, company) -> list[Posting]  raises on failure
"""
from . import (ashby, bamboohr, eightfold, greenhouse, hibob, join, jsonld, lever, oracle, personio, phenom, recruitee,
               smartrecruiters, successfactors, taleo, teamtailor, umantis, workday, workday_sitemap)

PROVIDERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "smartrecruiters": smartrecruiters,
    "recruitee": recruitee,
    "personio": personio,
    "workday": workday,
    "jsonld": jsonld,
    "successfactors": successfactors,
    "phenom": phenom,
    "oracle": oracle,
    "eightfold": eightfold,
    "taleo": taleo,
    "workday_sitemap": workday_sitemap,
    "teamtailor": teamtailor,
    "bamboohr": bamboohr,
    "umantis": umantis,
    "hibob": hibob,
    "join": join,
}
