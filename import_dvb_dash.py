"""CLI da Etapa 5.2b para importar um pacote DVB-DASH extraído."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dvb_dash_importer import DVB_VVC_SOURCE_URL, import_dvb_dash


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Lê um MPD DVB-DASH local, mede os segmentos .m4s e gera o "
            "manifesto aceito pelo simulador"
        )
    )
    parser.add_argument("--mpd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package-name")
    parser.add_argument("--sequence")
    parser.add_argument("--source-url", default=DVB_VVC_SOURCE_URL)
    parser.add_argument(
        "--attribution",
        required=True,
        help="texto de atribuição exibido para o pacote na página da DVB",
    )
    parser.add_argument("--license-name")
    parser.add_argument("--license-url")
    parser.add_argument(
        "--archive",
        type=Path,
        help="ZIP original opcional, usado para registrar tamanho e SHA-256",
    )
    parser.add_argument(
        "--representation",
        action="append",
        dest="representations",
        help="Representation@id a importar; pode ser repetido (padrão: todas)",
    )
    parser.add_argument(
        "--segments",
        type=int,
        help="limita a importação aos primeiros N segmentos",
    )
    parser.add_argument("--provenance", type=Path)
    parser.add_argument(
        "--protocol-template",
        type=Path,
        help="JSON-base cujo manifesto e escada serão atualizados",
    )
    parser.add_argument(
        "--protocol-config",
        type=Path,
        help="destino do protocolo adaptado; requer --protocol-template",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = import_dvb_dash(
        args.mpd,
        args.output,
        package_name=args.package_name,
        sequence=args.sequence,
        source_url=args.source_url,
        attribution=args.attribution,
        license_name=args.license_name,
        license_url=args.license_url,
        archive_path=args.archive,
        representation_ids=args.representations,
        max_segments=args.segments,
        provenance_path=args.provenance,
        protocol_template_path=args.protocol_template,
        protocol_config_path=args.protocol_config,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["adaptive_ladder"]:
        print(
            "Aviso: o pacote selecionado contém uma única representação; "
            "ele valida o fluxo, mas não permite adaptação de bitrate."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
