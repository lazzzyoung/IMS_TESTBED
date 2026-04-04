import json
import subprocess
from typing import Annotated

import typer

from volte_mutation_fuzzer.infra.core import InfraManager, check_ue_route, setup_ue_route

app = typer.Typer(
    add_completion=False,
    help="Manage the local Open5GS + Kamailio IMS Docker infrastructure.",
)


def _echo_process_result(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        typer.echo(result.stdout.rstrip())
    if result.stderr:
        typer.echo(result.stderr.rstrip(), err=True)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode or 1)


@app.command("build")
def build_command() -> None:
    _echo_process_result(InfraManager().build())


@app.command("up")
def up_command(
    detach: Annotated[bool, typer.Option("--detach/--foreground")] = True,
) -> None:
    _echo_process_result(InfraManager().up(detach=detach))


@app.command("down")
def down_command() -> None:
    _echo_process_result(InfraManager().down())


@app.command("status")
def status_command() -> None:
    _echo_process_result(InfraManager().status())


@app.command("provision")
def provision_command(
    count: Annotated[int, typer.Option("--count", min=1)] = 1,
    start_imsi: Annotated[str, typer.Option("--start-imsi")] = "001010000000001",
    start_msisdn: Annotated[str, typer.Option("--start-msisdn")] = "222222",
    key: Annotated[str, typer.Option("--key")] = "00112233445566778899AABBCCDDEEFF",
    opc: Annotated[str, typer.Option("--opc")] = "00112233445566778899AABBCCDDEEFF",
    amf: Annotated[str, typer.Option("--amf")] = "8000",
) -> None:
    provisioned = InfraManager().provision_subscribers(
        count=count,
        start_imsi=start_imsi,
        start_msisdn=start_msisdn,
        key=key,
        opc=opc,
        amf=amf,
    )
    typer.echo(json.dumps(provisioned, ensure_ascii=False, indent=2, sort_keys=True))


@app.command("setup-route")
def setup_route_command(
    ims_subnet: Annotated[str, typer.Option("--ims-subnet")] = "10.20.20.0/24",
    upf_ip: Annotated[str, typer.Option("--upf-ip")] = "172.22.0.8",
) -> None:
    result = setup_ue_route(ims_subnet=ims_subnet, upf_ip=upf_ip)
    typer.echo(
        json.dumps(
            {"ok": result.ok, "detail": result.detail},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if not result.ok:
        raise typer.Exit(code=1)


@app.command("check-route")
def check_route_command(
    ims_subnet: Annotated[str, typer.Option("--ims-subnet")] = "10.20.20.0/24",
) -> None:
    result = check_ue_route(ims_subnet=ims_subnet)
    typer.echo(
        json.dumps(
            {"ok": result.ok, "detail": result.detail},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if not result.ok:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
