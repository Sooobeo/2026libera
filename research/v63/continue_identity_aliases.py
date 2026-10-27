"""Explicit issuer name aliases; CIK/SIC verified by the SEC issuer response."""
import json,re
from pathlib import Path
from continue_sic_mapping import norm
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/v63_20261027/continuation_sources'
aliases={
 'charlesschwab':316709,'elililly':59478,'ge':40545,'geaerospace':40545,
 'taiwansemiconductormanufacturing':1046179,'taiwansemiconductormanufacturingcotwd':1046179,'taiwansemiconductormanufacturingcoltdtwd':1046179,
 'tjxcos':109198,'tjx':109198,'asml':937966,'asmlholdingnvdepositoryreceipt':937966,
 'goldmansachs':886982,'marshandmclennan':62709,'marshandmclennancos':62709,
 'telefonaktiebolagetlmericsson':717826,'jbhunttransportservices':728535,
 'novonordiska':353278,'aegonltdnyshs':769218,
 'lowescos':60667,'esteelaudercos':1001250,'drhorton':882184,'rocketc':1805284,
 'ibm':51143,'bancosantander':891478,'carnival':815097,
 'whirlpool':106640,'celanese':1306830,'vf':103379,'willscot':1647088,
 'roche':889131,'siemens':940418,
}
data=json.loads((OUT/'issuer_match_proposals.json').read_text());out={}
for r in data:
    if r['confirmed_cik']:continue
    n=norm(r['name'])
    if n in aliases:
        out[r['name']]={'confirmed_cik':aliases[n],'identity_method':'explicit_name_alias_to_SEC_issuer_record','identity_note':'Named issuer alias only; SIC obtained from fetched SEC submission JSON, not inferred from this alias.'}
(OUT/'issuer_identity_overrides.json').write_text(json.dumps(out,indent=2),encoding='utf8');print('aliases',len(out))
