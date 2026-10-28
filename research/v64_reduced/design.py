"""Pure, parameterized reduced schedules and offline inputs; never calls a model.

The original v6.3 modules and their global selectors are never changed.
Scope is supplied by a separate design manifest. A draft can prepare inputs,
but this module does not authorize execution or certify protocol completion.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
from itertools import combinations
from pathlib import Path

from research.v63 import build_run as original
from research.v63 import numerics
from research.v63.retrieval import canonical, sha
from research.v63.runtime import planned_schedule

PHASES = ('development-pilot', 'B-main', 'x-replacement', 'negative-control', 'A', 'C')
SUPPORTED_MAIN_COUNTS = (1, 2, 3, 6, 12)
FUNDS = ('F01', 'F02', 'F03', 'F04')
ARMS = ('R0', 'R1', 'R2', 'R3', 'C-context')
ORIGINAL_SCHEDULE_SHA256 = 'b2dd46acd001ffef04566df7e2bc128902b9224941a4fd5ce30f0ca6c27d77dd'
ORIGINAL_SOURCE_SHA256 = {
    'runtime.py':'3bcb3ae9d07d2477690c49ff36a8a0e0cc3a949208b7aceedd219d5f2e629050',
    'numerics.py':'b8906ee2cf06a8c9b51dac2f73ea8584a09d998a618e94879ca05b39e4236dd7',
    'build_run.py':'6bb784a76579f46cb41a121c66149db2b4868a91f21b78e6c33d970e3542d294',
}


def _original_schedule():
    rows = planned_schedule()
    if len(rows) != 3272 or sha(canonical(rows)) != ORIGINAL_SCHEDULE_SHA256:
        raise ValueError('Original frozen v6.3 schedule differs from the reviewed derivation.')
    return rows


def precision(scenario_id):
    return (0.5, 1.0, 2.0)[(int(scenario_id.rsplit('-', 1)[1])-1) % 3]


def original_target_cells():
    """Earliest original scenario in each precision x replacement-fund cell."""
    targets = {}
    for row in _original_schedule():
        if row['block'] == 'x-replacement':
            old = targets.setdefault(row['scenario'], row['fund_id'])
            if old != row['fund_id']:
                raise ValueError('Conflicting original replacement targets.')
    first = {}
    for scenario, target in sorted(targets.items()):
        first.setdefault((precision(scenario), target), scenario)
    if len(targets) != 60 or len(first) != 12:
        raise ValueError('Original 3 x 4 replacement target cells are incomplete.')
    return [dict(precision=r, replacement_target_fund=fund, scenario_id=sid)
            for (r, fund), sid in sorted(first.items())]


def choose_main_scenarios(count):
    """Outcome-blind metadata selection; small N cannot retain all 12 cells."""
    if type(count) is not int or count not in SUPPORTED_MAIN_COUNTS:
        raise ValueError('Supported main scenario counts: 1, 2, 3, 6, 12.')
    cells = original_target_cells()
    def score(choice):
        counts = Counter(row['precision'] for row in choice)
        values = [counts[r] for r in (.5, 1., 2.)]
        return (max(values)-min(values),
                -len({row['replacement_target_fund'] for row in choice}),
                tuple(sorted(row['scenario_id'] for row in choice)))
    chosen = min(combinations(cells, count), key=score)
    return sorted(row['scenario_id'] for row in chosen)


def make_design(*, main_scenarios=12, development_scenarios=3,
                negative_scenarios=4, enabled_phases=PHASES):
    """Create a reviewable specification, not an execution configuration."""
    if type(development_scenarios) is not int or not 1 <= development_scenarios <= 12:
        raise ValueError('Development scenario count must be 1..12.')
    if type(negative_scenarios) is not int or not 1 <= negative_scenarios <= 8:
        raise ValueError('Negative-control scenario count must be 1..8.')
    phases = list(enabled_phases)
    if not phases or len(phases) != len(set(phases)) or set(phases)-set(PHASES):
        raise ValueError('Enabled phases must be a nonempty unique subset of the six experiment types.')
    if 'x-replacement' in phases and 'B-main' not in phases:
        raise ValueError('Counterfactual execution requires its same-design B-main baseline.')
    return {
        'schema':'libera_reduced_schedule_specification_v1',
        'enabled_phases':[phase for phase in PHASES if phase in phases],
        'main_scenario_ids':choose_main_scenarios(main_scenarios),
        'development_scenario_ids':[f'development-{i:03d}' for i in range(1, development_scenarios+1)],
        'negative_control_scenario_ids':[f'negative_control-{i:03d}' for i in range(1, negative_scenarios+1)],
        'replicates':1, 'stages_per_trajectory':3, 'fresh_generation_required':True,
        'historical_005_responses_credited_to_new_design':0,
        'selection_rule':'Earliest representative of each original precision x replacement-target cell; among subsets minimize precision count imbalance, maximize distinct target funds, then choose the lexicographically earliest scenario-ID tuple. No outcome values are inputs.',
        'original_schedule_sha256':ORIGINAL_SCHEDULE_SHA256,
    }


def validate_design(design):
    if not isinstance(design, dict) or design.get('schema') != 'libera_reduced_schedule_specification_v1':
        raise ValueError('A reduced schedule specification is required.')
    try:
        expected = make_design(main_scenarios=len(design['main_scenario_ids']),
                               development_scenarios=len(design['development_scenario_ids']),
                               negative_scenarios=len(design['negative_control_scenario_ids']),
                               enabled_phases=design['enabled_phases'])
    except (KeyError, TypeError) as exc:
        raise ValueError('Malformed reduced schedule specification.') from exc
    if design != expected:
        raise ValueError('Design differs from the deterministic metadata-only selection or fresh-run policy.')
    return deepcopy(design)


def select_phase_schedule(phase, smoke_fund_id, *, design=None):
    # smoke_fund_id is retained solely for the original builder interface.
    # Every selected experiment keeps all required funds/labels.
    specification = validate_design(design) if design is not None else make_design()
    if phase not in PHASES:
        raise ValueError('Unknown reduced experiment phase.')
    if phase not in specification['enabled_phases']:
        return []
    selected = []
    for row in _original_schedule():
        if row['replicate'] != 1:
            continue
        if phase == 'development-pilot':
            keep = row['block']=='B-development' and row['scenario'] in specification['development_scenario_ids']
        elif phase in ('B-main','x-replacement'):
            keep = row['block']==phase and row['scenario'] in specification['main_scenario_ids']
        elif phase == 'negative-control':
            keep = row['block']==phase and row['scenario'] in specification['negative_control_scenario_ids']
        else:
            keep = row['block']=='actual-documents' and row['module']==phase
        if keep:
            selected.append(deepcopy(row))
    return selected


def phase_counts(design):
    design = validate_design(design)
    return {phase:len(select_phase_schedule(phase, None, design=design)) for phase in PHASES}


def derivation_metadata(design):
    design = validate_design(design)
    cells = [row for row in original_target_cells() if row['scenario_id'] in design['main_scenario_ids']]
    counts = phase_counts(design)
    return {
        'design_sha256':sha(canonical(design)), 'original_schedule_sha256':ORIGINAL_SCHEDULE_SHA256,
        'original_source_sha256':dict(ORIGINAL_SOURCE_SHA256),
        'main_precision_target_cells':cells,
        'main_precision_counts':{str(r):sum(row['precision']==r for row in cells) for r in (.5,1.,2.)},
        'main_precision_target_cells_retained':len(cells), 'main_precision_target_cells_original':12,
        'negative_control_source_mapping':[
            {'scenario_id':sid, 'source_fund_id':f'F{(int(sid.rsplit("-",1)[1])-1)%4+1:02d}',
             'precision':precision(sid), 'virtual_labels':['N01','N02','N03','N04']}
            for sid in design['negative_control_scenario_ids']],
        'phase_trajectories':counts, 'total_trajectories':sum(counts.values()),
        'logical_stages':3*sum(counts.values()), 'historical_responses_credited':0,
        'original_3272_trajectory_protocol_complete':False,
        'model_call_note':'Logical stages are planned workflow slots, not guaranteed API request counts.',
    }


def _load_manifest(root, config):
    if not config.get('design_manifest_path'):
        raise ValueError('Explicit design_manifest_path is required; no implicit runnable scope.')
    path = (root/config['design_manifest_path']).resolve()
    if root not in path.parents:
        raise ValueError('Design manifest must be inside the workspace.')
    manifest = original.read_json(path)
    design = validate_design(manifest.get('design'))
    return path, design


def build_phase(root, config, phase, tokenizer):
    """Build only selected cases; compute no reference bank and send no requests.

    Full original cheap scenario arrays are generated before selecting rows.
    CF replacement draws also use all 60 original cases, preserving the RNG
    stream. Only selected scenarios reach the subsequent numerical bank builder.
    """
    root = Path(root).resolve()
    manifest_path, design = _load_manifest(root, config)
    schedule = select_phase_schedule(phase, config.get('smoke_fund_id'), design=design)
    if not schedule:
        raise ValueError('Requested phase is disabled in this design.')
    for name, expected in ORIGINAL_SOURCE_SHA256.items():
        if hashlib.sha256((root/'research/v63'/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Original source changed: '+name)
    period = 'development' if phase=='development-pilot' else ('C' if phase=='C' else 'A_B')
    profiles = original.load_profiles(root/config['profiles_path'], period, funds=list(FUNDS))
    mandate_units = original.load_mandate_units(root/config['mandate_atomic_units_path']) if config.get('mandate_atomic_units_path') else {}
    calibration = numerics.calibrate(root)
    scenarios, hidden, replacements = [], [], []
    wanted = {row['scenario'] for row in schedule}
    if phase not in ('A','C'):
        block = 'development' if phase=='development-pilot' else ('negative_control' if phase=='negative-control' else 'main')
        all_scenarios, all_hidden = numerics.generate_scenarios(calibration, block)
        if phase == 'x-replacement':
            all_replacements = numerics.replacement_signals(calibration, all_scenarios, all_hidden)
            replacements = [deepcopy(row) for row in all_replacements if row['scenario_id'] in wanted]
            expected_targets = {row['scenario']:row['fund_id'] for row in schedule}
            if {row['scenario_id']:row['fund_id'] for row in replacements} != expected_targets:
                raise ValueError('Original counterfactual targets differ from selected schedule.')
        scenarios = [deepcopy(row) for row in all_scenarios if row['scenario_id'] in wanted]
        hidden = [deepcopy(row) for row in all_hidden if row['scenario_id'] in wanted]
        if len(scenarios)!=len(wanted) or len(hidden)!=len(wanted) or {s['scenario_id'] for s in scenarios}!=wanted or {s['scenario_id'] for s in hidden}!=wanted:
            raise ValueError('Selected frozen scenario/hidden metadata is missing or duplicated.')
    lookup = {row['scenario_id']:row for row in scenarios}
    for replacement in replacements:
        lookup[replacement['scenario_id']]['private_signals'][replacement['fund_id']] = deepcopy(replacement['replacement_x'])
    cases, entries = {}, []
    for row in schedule:
        key = row['scenario']+'__'+row['fund_id']
        fund = row['fund_id']
        if key not in cases:
            if phase in ('A','C'):
                cases[key] = original.actual_document_input(profiles[fund], calibration, phase, root/config['documents_path'], tokenizer)
            elif phase == 'negative-control':
                index = int(row['scenario'].rsplit('-',1)[1])-1
                source = f'F{index%4+1:02d}'
                scenario = deepcopy(lookup[row['scenario']])
                same = scenario['private_signals']['F01']
                scenario['private_signals'] = {f'N{i:02d}':deepcopy(same) for i in range(1,5)}
                profile = deepcopy(profiles[source])
                profile.update(source_fund_id=source, fund_id=fund)
                cases[key] = original.b_input(profile, calibration, scenario, tokenizer, fund_id=fund, mandate_units=mandate_units)
            else:
                cases[key] = original.b_input(profiles[fund], calibration, lookup[row['scenario']], tokenizer, mandate_units=mandate_units)
        entries.append({**row, 'case_id':key, 'input_sha256':sha(canonical(cases[key]))})
    return {
        'phase':phase, 'profiles':profiles, 'calibration':calibration,
        'scenarios_evaluator_only':scenarios, 'hidden_evaluator_only':hidden,
        'cases':cases, 'entries':entries,
        'replacement_assignments':[{'scenario_id':r['scenario_id'],'fund_id':r['fund_id']} for r in replacements],
        'logical_stages':3*len(entries), 'human_review_mode':'user_assumed_completed',
        'mandate_units_audit':mandate_units,
        'design_manifest':original.file_ref(manifest_path, root),
        'schedule_derivation':derivation_metadata(design),
        'fresh_generation_required':True, 'historical_responses_credited':0,
    }
