"""Local code-kit construction and verification; no deployment or publication."""
import json
from pathlib import Path
import sys
import zipfile

from .local_kit import build_local_kit
from .kit_resources.verify_kit import verify_kit


def add_parser(subcommands):
    root = subcommands.add_parser('local-kit', help='build/verify a private fresh-workstation code kit; human trial stays separate')
    sub = root.add_subparsers(dest='kit_command', required=True)
    build = sub.add_parser('build')
    build.add_argument('--repo', type=Path, required=True)
    build.add_argument('--wheel', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--quiet', action='store_true')
    verify = sub.add_parser('verify')
    verify.add_argument('kit', type=Path)


def run_cli(args):
    try:
        value = (build_local_kit(args.repo, args.wheel, args.output, quiet=args.quiet) if args.kit_command == 'build'
                 else verify_kit(args.kit))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile) as exc:
        print('bridgeforge local-kit: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(value, indent=2))
    return 0 if value['state'] in {'LOCAL_TRIAL_KIT_READY', 'READY_FOR_LOCAL_TRIAL'} else 1
