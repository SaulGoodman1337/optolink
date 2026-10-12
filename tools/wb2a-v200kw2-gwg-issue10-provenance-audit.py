#!/usr/bin/env python3
"""Authentic historical OpenV issue10/245 discussion evidence, not a ROM reader.

The original wiki comments (2010, 2011, 2015) were imported into GitHub in
2017; dates are cited from original message headers, never GitHub created_at.
Offline SHA-pin raw *public* GitHub REST JSON retrieved on 2026-10-12.
No network while auditing, no serial/MCU IO, no dangerous command generation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

SOURCES={
 "issue10.json":"a30befa4e02f836f9c999db4bd573151af0de16c45f0d3aab989280df992eb87",
 "issue10-comments.json":"62da745448cb3d2b5516cb7a1451ba34f34cb81efbca066f93099373ad4da1a0",
 "issue245-comments.json":"07d68392d4931453fda0e2f7ccc7fb96ead9174026fc61dbdab5ad8128ac18c0",
}
SOURCE_URLS={
 "issue10.json":"https://api.github.com/repos/openv/openv/issues/10",
 "issue10-comments.json":"https://api.github.com/repos/openv/openv/issues/10/comments?per_page=100",
 "issue245-comments.json":"https://api.github.com/repos/openv/openv/issues/245/comments?per_page=100",
}
ISSUE10_URL="https://github.com/openv/openv/issues/10"
ISSUE245_COMMENT_URL="https://github.com/openv/openv/issues/245#issuecomment-339633725"
SCOPE_LIMIT_BYTES=50_000


class SourceRejected(ValueError):pass


def attested_json(raw:bytes,key:str):
    if key not in SOURCES:
        raise SourceRejected("unexpected source")
    if (type(raw) is not bytes or len(raw)>SCOPE_LIMIT_BYTES
        or hashlib.sha256(raw).hexdigest()!=SOURCES[key]):
        raise SourceRejected("public original source SHA mismatch")
    return json.loads(raw)


def imported_date(body:str)->str:
    # GitHub 'created_at' is 2017 re-import and MUST NEVER be presented as
    # the original discussion date.
    for line in body.splitlines():
        if line.startswith("* Date: "):
            return line[len("* Date: "):].strip()
    raise SourceRejected("2010-2015 original date not present")


def comments_by_id(items):
    if type(items) is not list:raise SourceRejected("original comments not list")
    ids=[x.get("id") for x in items]
    if len(set(ids))!=len(ids):raise SourceRejected("duplicate original comment")
    return {x["id"]:x for x in items}


def verify(original_issue:bytes,original_comments:bytes,old_forum_comments:bytes)->dict:
    issue=attested_json(original_issue,"issue10.json")
    comments=comments_by_id(attested_json(original_comments,"issue10-comments.json"))
    forum=comments_by_id(attested_json(old_forum_comments,"issue245-comments.json"))
    if (issue.get("number")!=10 or issue.get("html_url")!=ISSUE10_URL
        or issue.get("created_at")!="2017-10-25T15:32:47Z"):
        raise SourceRejected("2010 original was not imported as expected")
    body=issue["body"]
    if (imported_date(body)!="Mon,  1 Nov 2010 22:05:36 UT"
        or "* From: TerminatorIII" not in body
        or "01 C7 F8 04 04" not in body or "20 98 00 02" not in body):
        raise SourceRejected("historical GWG identity exchange not attested")
    if set(comments)!={339370647,339370668,339371859}:
        raise SourceRejected("unexpected issue10 comment inventory")
    hsp=comments[339370647]["body"]
    dev=comments[339371859]["body"]
    question=comments[339370668]["body"]
    if (imported_date(hsp)!="Mon,  1 Nov 2010 23:07:53 UT"
        or "* From: vitoopen" not in hsp
        or "GWG Protokoll zu verwenden" not in hsp
        or "allen Steuerungen unterstützt" not in hsp
        or 'ein "höheres" verwendet werden' not in hsp
        or "voIdent" not in hsp):
        raise SourceRejected("universal GWG identification rule missing")
    if (imported_date(question)!="Tue,  2 Nov 2010 08:23:32 UT"
        or "0 bis 65536" not in question
        or "Dump der Firmware" not in question):
        raise SourceRejected("original user scan-proposal missing")
    if (imported_date(dev)!="Mon, 17 Jan 2011 17:53:16 UT"
        or "* From: TerminatorIII" not in dev
        or "in eine Binärdatei schreiben" not in dev
        or "über 0x8000 keine Daten mehr gibt" not in dev):
        raise SourceRejected("real independent 2011 normal scan limit missing")
    quoted=forum.get(339633725,{}).get("body","")
    if (imported_date(quoted)!="Fri,  8 May 2015 22:46:54 UT"
        or "früheren (privaten) Forum vom 17.01.2009" not in quoted
        or "01 AD 07 01 FB 04" not in quoted
        or "aus Sicherheitsgründen" not in quoted):
        raise SourceRejected("2009 private forum excerpt unavailable")
    if (len(forum)!=6 or 339633760 not in forum
        or "Physical Read (und nicht EEPROM)" not in forum[339633760]["body"]):
        raise SourceRejected("contemporaneous 2015 forum context missing")
    frame=bytes.fromhex("01 C7 F8 04 04")
    if frame!=bytes((1,0xc7,0xf8,4,4)):
        raise SourceRejected("not standard GWG virtual-read layout")
    return {
        "mode":"OFFLINE_SHA_ATTESTED_V200KW2_GWG_PRIMARY_SOURCE_AND_PRIVATE_FORUM_TRACE",
        "retrieval_date":"2026-10-12",
        "github_imported_2017":True,
        "original_discussion_start_date":"2010-11-01",
        "sha256":SOURCES,
        "source_urls":SOURCE_URLS,
        "historical_source":ISSUE10_URL,
        "historical_2010_controller":"V200KW2",
        "historical_2010_GWG_virtual_read_frame":frame.hex(),
        "historical_2010_identity_response":"20980002",
        "GWG_opcode_C7_virtual_read_accepted_by_old_200KW2":True,
        "historical_2010_GWG_physical_read_CB_accepted_proven":False,
        "historical_2010_GWG_xram_read_C5_accepted_proven":False,
        "historical_2010_universal_gwg_identification_reported_by_vitoopen":True,
        "2011_user_straight_address_dump_attempt_reported":True,
        "2011_user_reported_no_data_above":"0x8000",
        "2011_user_address_dump_firmware_is_not_KarlKoch_success_claim":True,
        "2015_embedded_private_2009_developer_forum_quote_found":True,
        "private_forum_survivor":ISSUE245_COMMENT_URL,
        "private_forum_quote_2009_is_about_EEPROM_WRITE_not_ROM_READ":True,
        "safe_controllertest_ready":False,
        "original_firmware_dump_request_sequence_recovered":False,
        "WB2A_GWG_read_subopcodes_proven":False,
        "controller_io":0,"controller_writes":0,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_directory",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if not a.source_directory.is_dir() or a.source_directory.is_symlink():
        p.error("source directory must be existing, not a symlink")
    sources=[]
    for key in SOURCES:
        f=a.source_directory/key
        if f.is_symlink() or not f.is_file() or f.stat().st_size>SCOPE_LIMIT_BYTES:
            p.error("only three exact public originals allowed")
        sources.append(f.read_bytes())
    report=verify(*sources)
    text=json.dumps(report,sort_keys=True,indent=2)+"\n"
    if a.out:a.out.write_text(text)
    print(text)


if __name__=="__main__":main()
