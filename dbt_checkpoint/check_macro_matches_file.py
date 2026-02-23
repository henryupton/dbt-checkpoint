import argparse
import os
import time
from collections import defaultdict
from typing import Any, Dict, Optional, Sequence

from dbt_checkpoint.tracking import dbtCheckpointTracking
from dbt_checkpoint.utils import (
    JsonOpenError,
    add_default_args,
    get_dbt_manifest,
    get_filenames,
    get_macro_sqls,
    get_missing_file_paths,
    red,
)


def check_macro_matches_file(
    paths: Sequence[str], manifest: Dict[str, Any], exclude_pattern: str
) -> int:
    paths = get_missing_file_paths(paths, manifest, exclude_pattern=exclude_pattern)
    status_code = 0
    sqls = get_macro_sqls(paths, manifest)

    # Group macros by file path
    macros_by_file = defaultdict(list)
    macros = manifest.get("macros", {})

    for key, macro in macros.items():
        path = macro.get("path")
        if path in sqls.values():
            macro_name = macro.get("name")
            macros_by_file[path].append(macro_name)

    # Check each file
    for file_path, macro_names in macros_by_file.items():
        # Check if more than one macro in file
        if len(macro_names) > 1:
            status_code = 1
            print(
                f"{red(file_path)}: "
                f"contains {len(macro_names)} macros ({', '.join(macro_names)}). "
                f"Each macro should be in its own file."
            )
            continue

        # Check if macro name matches file name
        if len(macro_names) == 1:
            macro_name = macro_names[0]
            file_name = os.path.splitext(os.path.basename(file_path))[0]

            if macro_name != file_name:
                status_code = 1
                print(
                    f"{red(file_path)}: "
                    f"macro name '{macro_name}' does not match file name '{file_name}.sql'."
                )

    return status_code


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    add_default_args(parser)

    args = parser.parse_args(argv)

    try:
        manifest = get_dbt_manifest(args)
    except JsonOpenError as e:
        print(f"Unable to load manifest file ({e})")
        return 1

    start_time = time.time()
    status_code = check_macro_matches_file(
        paths=args.filenames, manifest=manifest, exclude_pattern=args.exclude
    )
    end_time = time.time()
    script_args = vars(args)

    tracker = dbtCheckpointTracking(script_args=script_args)
    tracker.track_hook_event(
        event_name="Hook Executed",
        manifest=manifest,
        event_properties={
            "hook_name": os.path.basename(__file__),
            "description": "Check macro matches file name.",
            "status": status_code,
            "execution_time": end_time - start_time,
            "is_pytest": script_args.get("is_test"),
        },
    )

    return status_code


if __name__ == "__main__":
    exit(main())
