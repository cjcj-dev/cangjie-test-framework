import json
from pathlib import Path

from maple_test import configs
from maple_test.utils import filter_command_line


def audit_directives(case, lines, condition, run_script, extract_dependence):
    driver = 'active' if case.commands else 'unknown'
    if not case.commands:
        try:
            commands = [filter_command_line(line, condition, run_script,
                                            configs.get_val("compatible"), ignore_guard=True)
                        for line in lines]
        except (ValueError, SystemExit):
            # An invalid directive in a closed branch cannot prove inapplicability.
            pass
        else:
            if any(commands):
                driver = 'inactive'
    active = case.dependence
    try:
        declared = extract_dependence(lines, condition, ignore_guard=True)
    except ValueError:
        # Maple accepted the active subset; an invalid closed directive adds no evidence.
        declared = active
    return driver, sorted(declared | active)


def write_plan(plan, task, cases, expand):
    files = []
    for rel, case in sorted(cases.items()):
        state = 'selected' if case.relative_path != '' else (
            'decode-error' if getattr(case, 'decode_error', False) else 'excluded')
        driver, declared = getattr(case, 'llt_audit', ('unknown', []))
        config = task.config.get_case_config(case) if declared else None
        dependencies = []
        for token in declared:
            source = case.path.parent / expand(token, config)
            kind = 'file' if source.is_file() else 'directory' if source.is_dir() else 'missing'
            dependencies.append(dict(token=token, enabled=token in case.dependence,
                                     source=str(source.resolve()) if kind != 'missing' else str(source),
                                     kind=kind))
        files.append((rel, dict(state=state, driver=driver, dependencies=dependencies)))
    with Path(plan).open('a', encoding='utf-8') as stream:
        print(json.dumps(dict(scope=str(task.path), cfg=str(task.cfg_path),
                              condition=sorted(task.condition), files=files)), file=stream)
