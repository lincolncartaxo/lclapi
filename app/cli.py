from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from .service import import_path


def main() -> None:
    parser = argparse.ArgumentParser(prog='precos-api')
    sub = parser.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import', help='Importa um ZIP/XLSX SINAPI ou 7Z SICRO')
    imp.add_argument('path', type=Path)
    imp.add_argument('--dry-run', action='store_true')
    watch = sub.add_parser('watch', help='Importa automaticamente arquivos novos em uma pasta')
    watch.add_argument('directory', type=Path)
    watch.add_argument('--interval', type=int, default=10)
    args = parser.parse_args()
    if args.command == 'import':
        print(json.dumps(import_path(args.path, dry_run=args.dry_run), ensure_ascii=False, indent=2, default=str))
        return
    args.directory.mkdir(parents=True, exist_ok=True)
    done = args.directory / '.processed'
    done.mkdir(exist_ok=True)
    print(f'Observando {args.directory}...')
    while True:
        for path in sorted(args.directory.iterdir()):
            if path.is_file() and path.suffix.lower() in {'.zip', '.7z', '.xlsx'} and not (done / path.name).exists():
                try:
                    result = import_path(path)
                    print(json.dumps(result, ensure_ascii=False, default=str))
                    shutil.move(str(path), done / path.name)
                except Exception as exc:
                    print(json.dumps({'file': path.name, 'error': str(exc)}, ensure_ascii=False))
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
