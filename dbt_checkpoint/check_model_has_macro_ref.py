import argparse
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Set

from dbt_checkpoint.tracking import dbtCheckpointTracking
from dbt_checkpoint.utils import (
    JsonOpenError,
    add_default_args,
    get_dbt_manifest,
    get_missing_file_paths,
    get_model_sqls,
    get_models,
    red,
)


def _macro_names_from_ids(macro_ids: List[str]) -> Set[str]:
    return {mid.split(".")[-1] for mid in macro_ids}


def check_model_has_macro_ref(
    paths: Sequence[str],
    manifest: Dict[str, Any],
    exclude_pattern: str,
    require_macros: List[str],
    forbid_macros: List[str],
    include_disabled: bool = False,
) -> int:
    paths = get_missing_file_paths(
        paths, manifest, extensions=[".sql"], exclude_pattern=exclude_pattern
    )
    status_code = 0
    sqls = get_model_sqls(paths, manifest, include_disabled)
    filenames = set(sqls.keys())

    for model in get_models(manifest, filenames, include_disabled=include_disabled):
        referenced = _macro_names_from_ids(
            model.node.get("depends_on", {}).get("macros", [])
        )
        file_path = model.node.get("original_file_path", model.filename)

        for required in require_macros:
            if required not in referenced:
                status_code = 1
                print(
                    f"{red(file_path)}: "
                    f"model '{model.model_name}' does not reference required macro '{required}'."
                )

        for forbidden in forbid_macros:
            if forbidden in referenced:
                status_code = 1
                print(
                    f"{red(file_path)}: "
                    f"model '{model.model_name}' references forbidden macro '{forbidden}'."
                )

    return status_code


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    add_default_args(parser)
    parser.add_argument(
        "--require-macros",
        nargs="*",
        default=[],
        dest="require_macros",
        help="Macros that must be referenced by the model.",
    )
    parser.add_argument(
        "--forbid-macros",
        nargs="*",
        default=[],
        dest="forbid_macros",
        help="Macros that must not be referenced by the model.",
    )

    args = parser.parse_args(argv)

    try:
        manifest = get_dbt_manifest(args)
    except JsonOpenError as e:
        print(f"Unable to load manifest file ({e})")
        return 1

    start_time = time.time()
    status_code = check_model_has_macro_ref(
        paths=args.filenames,
        manifest=manifest,
        exclude_pattern=args.exclude,
        require_macros=args.require_macros or [],
        forbid_macros=args.forbid_macros or [],
        include_disabled=args.include_disabled,
    )
    end_time = time.time()
    script_args = vars(args)

    tracker = dbtCheckpointTracking(script_args=script_args)
    tracker.track_hook_event(
        event_name="Hook Executed",
        manifest=manifest,
        event_properties={
            "hook_name": os.path.basename(__file__),
            "description": "Check model references required/forbidden macros.",
            "status": status_code,
            "execution_time": end_time - start_time,
            "is_pytest": script_args.get("is_test"),
        },
    )

    return status_code


if __name__ == "__main__":
    exit(main())
