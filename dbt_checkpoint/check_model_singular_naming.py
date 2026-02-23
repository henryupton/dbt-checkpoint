import argparse
import os
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Set

from dbt_checkpoint.tracking import dbtCheckpointTracking
from dbt_checkpoint.utils import (
    JsonOpenError,
    add_default_args,
    get_dbt_manifest,
    get_filenames,
    get_missing_file_paths,
    get_models,
    red,
    yellow,
)

try:
    import inflect
except ImportError:
    inflect = None


def extract_words_from_name(name: str) -> List[str]:
    """
    Extract words from a model name, handling various separators.

    Examples:
        'fact_customers' -> ['fact', 'customers']
        'dim_user_orders' -> ['dim', 'user', 'orders']
        'stg_sales_data' -> ['stg', 'sales', 'data']
    """
    # Split by common separators: underscore, hyphen, space
    words = re.split(r'[_\-\s]+', name.lower())
    # Filter out empty strings
    return [w for w in words if w]


def check_model_singular_naming(
    paths: Sequence[str],
    manifest: Dict[str, Any],
    exclude_pattern: str,
    exclude_words: Set[str],
    include_disabled: bool = False,
) -> Dict[str, Any]:
    """
    Check that model names use singular form of words.

    Args:
        paths: List of file paths to check
        manifest: dbt manifest dictionary
        exclude_pattern: Regex pattern to exclude files
        exclude_words: Set of words to exclude from plural checking
        include_disabled: Whether to include disabled models

    Returns:
        Dictionary with status_code and details
    """
    if inflect is None:
        print(
            f"{red('Error')}: The 'inflect' library is required for this hook. "
            f"Install it with: pip install inflect"
        )
        return {"status_code": 1}

    paths = get_missing_file_paths(
        paths, manifest, extensions=[".sql"], exclude_pattern=exclude_pattern
    )

    status_code = 0
    sqls = get_filenames(paths, [".sql"])
    filenames = set(sqls.keys())
    models = get_models(manifest, filenames, include_disabled=include_disabled)

    p = inflect.engine()

    for model in models:
        model_name = model.filename
        words = extract_words_from_name(model_name)
        plural_words = []

        for word in words:
            # Skip if word is in exclusion list
            if word in exclude_words:
                continue

            # Skip very short words (likely prefixes/acronyms)
            if len(word) <= 2:
                continue

            # Check if word is plural
            singular = p.singular_noun(word)
            if singular:  # singular_noun returns False if already singular, or the singular form if plural
                plural_words.append((word, singular))

        if plural_words:
            status_code = 1
            print(
                f"{red(model_name)}: model name contains plural words that should be singular:"
            )
            for plural, singular in plural_words:
                print(f"  - {yellow(plural)} -> {singular}")
            print()

    return {"status_code": status_code}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that model names use singular form of words."
    )
    add_default_args(parser)

    parser.add_argument(
        "--exclude-words",
        type=str,
        default="",
        help="Comma-separated list of words to exclude from plural checking (e.g., 'data,series,analytics,sales')",
    )

    args = parser.parse_args(argv)

    try:
        manifest = get_dbt_manifest(args)
    except JsonOpenError as e:
        print(f"Unable to load manifest file ({e})")
        return 1

    # Parse exclude words
    exclude_words = set()
    if args.exclude_words:
        exclude_words = {word.strip().lower() for word in args.exclude_words.split(",")}

    start_time = time.time()
    hook_properties = check_model_singular_naming(
        paths=args.filenames,
        manifest=manifest,
        exclude_pattern=args.exclude,
        exclude_words=exclude_words,
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
            "description": "Check model singular naming",
            "status": hook_properties.get("status_code"),
            "execution_time": end_time - start_time,
            "is_pytest": script_args.get("is_test"),
        },
    )

    return hook_properties.get("status_code")


if __name__ == "__main__":
    exit(main())
